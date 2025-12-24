import * as cdk from 'aws-cdk-lib';
import * as path from "path";
import { Construct } from 'constructs';
import * as dynamodb from "aws-cdk-lib/aws-dynamodb";
import * as lambda from "aws-cdk-lib/aws-lambda";
import * as apigwv2 from "aws-cdk-lib/aws-apigatewayv2"
import * as integrations from "aws-cdk-lib/aws-apigatewayv2-integrations"
import * as authorizers from "aws-cdk-lib/aws-apigatewayv2-authorizers"
import * as cognito from "aws-cdk-lib/aws-cognito"


export class FlowInfraStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    // Cognito user pool
    const userPool = new cognito.UserPool(this, "FlowUserPool", {
      selfSignUpEnabled: true,
      signInAliases:  {email: true},
      standardAttributes: {
        email: {required: true, mutable: true},
      },
      passwordPolicy: {
        minLength: 8, 
        requireLowercase: true,
        requireUppercase: true,
        requireDigits: true,
      },
      removalPolicy: cdk.RemovalPolicy.DESTROY, // for dev, gonna change to RETAIN later
    })

    const userPoolClient = new cognito.UserPoolClient(this, "FlowUserPoolClient", {
      userPool,
      generateSecret: false,
      authFlows: {
        userPassword: true,
        userSrp: true,
      },
    })

    // creating dynamo db table
    const notesTable = new dynamodb.Table(this, "FlowNotesTable", {
      partitionKey: {name: "userId", type: dynamodb.AttributeType.STRING },
      sortKey: { name: "noteId", type: dynamodb.AttributeType.STRING },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      removalPolicy: cdk.RemovalPolicy.DESTROY          // for dev
    })

    // creating lambda function
    const notesFn = new lambda.Function(this, "NotesHandlerFn", {
      runtime: lambda.Runtime.PYTHON_3_12,
      handler: "handler.handler",
      code: lambda.Code.fromAsset(
        path.join(__dirname, "../services/api/lambdas/notes")
      ),
      environment: {
        TABLE_NAME: notesTable.tableName,
      },
      timeout: cdk.Duration.seconds(10),
    })
    
    notesTable.grantReadWriteData(notesFn)

    const httpApi = new apigwv2.HttpApi(this, "FlowHttpApi", {
      corsPreflight: {
        allowHeaders: ["authorization", "content-type"],
        allowMethods: [
          apigwv2.CorsHttpMethod.GET,
          apigwv2.CorsHttpMethod.POST,
          apigwv2.CorsHttpMethod.PUT,
          apigwv2.CorsHttpMethod.DELETE,
          apigwv2.CorsHttpMethod.OPTIONS,
        ],
        allowOrigins: ["*"],
      },
    })

    const issuer = `https://cognito-idp.${this.region}.amazonaws.com/${userPool.userPoolId}`
    const jwtAuth = new authorizers.HttpJwtAuthorizer("FlowJwtAuthorizer", issuer, {
      jwtAudience: [userPoolClient.userPoolClientId],
    })

    const notesIntegration = new integrations.HttpLambdaIntegration(
      "NotesLambdaIntegration",
      notesFn
    )

    httpApi.addRoutes({
      path: "/notes",
      methods: [apigwv2.HttpMethod.GET, apigwv2.HttpMethod.POST],
      integration: notesIntegration,
      authorizer: jwtAuth,
    })

    httpApi.addRoutes({
      path: "/notes/{id}",
      methods: [apigwv2.HttpMethod.PUT, apigwv2.HttpMethod.DELETE],
      integration: notesIntegration,
      authorizer: jwtAuth,
    })

    new cdk.CfnOutput(this, "FlowApiUrl", { value: httpApi.url! })
    new cdk.CfnOutput(this, "FlowUserPoolId", { value: userPool.userPoolId })
    new cdk.CfnOutput(this, "FlowUserPoolClientId", {
      value: userPoolClient.userPoolClientId,
    })
    new cdk.CfnOutput(this, "FlowRegion", { value: this.region })


  }
}
