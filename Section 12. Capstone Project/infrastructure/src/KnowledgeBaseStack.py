import aws_cdk as cdk
from aws_cdk import (
    Stack,
    CfnOutput,
    Duration,
    aws_s3 as s3,
    aws_s3_deployment as s3deploy,
    aws_iam as iam,
    aws_bedrock as bedrock,
    aws_s3vectors as s3vectors,
    aws_cloudwatch as cloudwatch,
    custom_resources as cr,
)
from constructs import Construct
import os


class KnowledgeBaseStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # S3 bucket that holds your raw knowledge base documents
        data_source_bucket = s3.Bucket(
            self, "OrangeRAG-Source",
            removal_policy=cdk.RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        # Deploy local documents into the data source bucket under the "docs/" prefix
        local_asset_path = os.path.join(
            os.path.dirname(__file__), "../../assets/knowledgeBase"
        )
        bucketDeployment = s3deploy.BucketDeployment(
            self,
            "DeployMyAssets",
            sources=[s3deploy.Source.asset(local_asset_path)],
            destination_bucket=data_source_bucket,
            destination_key_prefix="docs",
            prune=False,
        )

        # S3 Vectors bucket and index that will back the Bedrock S3 vector store
        vector_bucket = s3vectors.CfnVectorBucket(
            self,
            "OrangeRAG-Vector",
        )
        vector_bucket.apply_removal_policy(cdk.RemovalPolicy.DESTROY)

        vector_index = s3vectors.CfnIndex(
            self,
            "OrangeRAG-Index",
            data_type="float32",
            dimension=1024,
            distance_metric="cosine",
            index_name="orange-electronic-rag-index",
            vector_bucket_arn=vector_bucket.attr_vector_bucket_arn,
            metadata_configuration=s3vectors.CfnIndex.MetadataConfigurationProperty(
                non_filterable_metadata_keys=["AMAZON_BEDROCK_TEXT", "AMAZON_BEDROCK_METADATA"]
            )
        )
        vector_index.apply_removal_policy(cdk.RemovalPolicy.DESTROY)
        
        # IAM role that Bedrock Knowledge Base assumes
        region = Stack.of(self).region
        embedding_model_arn = (
            f"arn:aws:bedrock:{region}::foundation-model/amazon.titan-embed-text-v2:0"
        )
        
        bedrock_kb_role = iam.Role(
            self,
            "OrangeRAG-Role",
            assumed_by=iam.ServicePrincipal("bedrock.amazonaws.com"),
            description="Role for Amazon Bedrock Knowledge Base to access S3 data source and S3 vector store.",
        )

        bedrock_kb_role_policy = iam.Policy(self, "InlinePolicy",
            statements=[
                iam.PolicyStatement(
                    actions=["bedrock:InvokeModel"],
                    resources=[embedding_model_arn]
                ),
                iam.PolicyStatement(
                    actions=[
                        "s3vectors:GetIndex",
                        "s3vectors:QueryVectors",
                        "s3vectors:PutVectors",
                        "s3vectors:GetVectors",
                        "s3vectors:DeleteVectors"
                    ],
                    resources=[vector_index.attr_index_arn],
                ),
                iam.PolicyStatement(
                    actions=["s3:ListBucket", "s3:GetObject", "s3:PutObject"],
                    resources=[
                        data_source_bucket.bucket_arn,
                        data_source_bucket.bucket_arn+"/*"
                    ]
                )
            ],
            force=True
        )

        bedrock_kb_role.attach_inline_policy(bedrock_kb_role_policy)

        # Create the Bedrock Knowledge Base with S3 Vectors as the vector store
        knowledge_base = bedrock.CfnKnowledgeBase(
            self,
            "OrangeRAG-KB",
            name="OrangeRAG-KB",
            role_arn=bedrock_kb_role.role_arn,
            knowledge_base_configuration={
                "type": "VECTOR",
                "vectorKnowledgeBaseConfiguration": {
                    "embeddingModelArn": embedding_model_arn,
                },
            },
            storage_configuration={
                # S3 Vectors is the vector store backing this knowledge base
                "type": "S3_VECTORS",
                "s3VectorsConfiguration": {
                    # Use the S3 Vectors index created above as the vector store
                    "indexArn": vector_index.attr_index_arn,
                },
            },
        )

        knowledge_base.node.add_dependency(bedrock_kb_role_policy)
        knowledge_base.node.add_dependency(bucketDeployment)

        CfnOutput(self, "OrangeKnowledgeBaseArn",
            value=knowledge_base.attr_knowledge_base_arn,
            export_name="OrangeKnowledgeBaseArn",
        )

        CfnOutput(self, "OrangeKnowledgeBaseId",
            value=knowledge_base.attr_knowledge_base_id,
            export_name="OrangeKnowledgeBaseId",
        )

        # Data source mapping from the existing S3 bucket (docs prefix) into the knowledge base
        data_source = bedrock.CfnDataSource(
            self,
            "OrangeRAG-S3Source",
            name="OrangeRAG-S3Source",
            knowledge_base_id=knowledge_base.attr_knowledge_base_id,
            data_source_configuration={
                "type": "S3",
                "s3Configuration": {
                    "bucketArn": data_source_bucket.bucket_arn,
                    "inclusionPrefixes": ["docs/"],
                },
            },
            data_deletion_policy="DELETE",
        )

        data_source.add_dependency(knowledge_base)

        # Trigger an initial ingestion job so the knowledge base is synchronized
        # with the S3 data source when this stack is deployed.
        sync_kb = cr.AwsCustomResource(
            self,
            "OrangeRAG-KBSync",
            on_create=cr.AwsSdkCall(
                service="BedrockAgent",
                action="startIngestionJob",
                parameters={
                    "knowledgeBaseId": knowledge_base.attr_knowledge_base_id,
                    "dataSourceId": data_source.attr_data_source_id,
                },
                physical_resource_id=cr.PhysicalResourceId.of(
                    "OrangeRAG-KBSync"
                ),
            ),
            policy=cr.AwsCustomResourcePolicy.from_statements(
                [
                    iam.PolicyStatement(
                        actions=["bedrock:StartIngestionJob"],
                        resources=["*"],
                    )
                ]
            ),
        )

        # Ensure sync runs only after the data source is fully created
        sync_kb.node.add_dependency(data_source)

        # CloudWatch Tier 1 Alarm
        cloudwatch.Alarm(
            self,
            "OrangeKnowledgeBaseErrors",
            alarm_name="OrangeKnowledgeBaseErrors",
            metric=cloudwatch.Metric(
                namespace="AWS/Bedrock",
                metric_name="RetrieveAndGenerateErrors",
                dimensions_map={
                    "KnowledgeBaseId": knowledge_base.attr_knowledge_base_id,
                },
                period=Duration.minutes(1),
                statistic="Sum",
            ),
            threshold=1,
            evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        )