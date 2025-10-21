from fastmcp import FastMCP
import boto3
import time
import json

app = FastMCP()
ec2 = boto3.client("ec2", region_name="ap-northeast-1")
s3 = boto3.client("s3", region_name="ap-northeast-1")

AMI_ID = "ami-xxxxxxxx"  # Claude実行可能なAMI
INSTANCE_PROFILE = "EC2ClaudeRunnerRole"
S3_BUCKET = "my-claude-results-bucket"  # S3バケットを事前作成しておく

# === 1️⃣ Claude実行 & 結果をS3にアップロード ===
@app.tool()
def run_claude_on_new_instance(prompt: str, instance_type="t3.medium"):
    """
    新しいEC2を起動し、Claude CLIでプロンプトを実行して結果をS3にアップロードします。
    """

    timestamp = str(int(time.time()))
    s3_key = f"claude-results/{timestamp}.txt"

    # === EC2 UserDataで実行されるスクリプト ===
    # Claude実行結果をS3にアップロード
    user_data_script = f"""#!/bin/bash
    set -ex
    apt update -y
    apt install -y python3-pip awscli
    pip install anthropic
    echo '{prompt}' > /root/prompt.txt

    # Claudeの実行結果をファイルに出力
    claude api chat --model claude-3-5-sonnet-20241022 --input-file /root/prompt.txt > /root/result.txt

    # AWS CLIでS3にアップロード
    aws s3 cp /root/result.txt s3://{S3_BUCKET}/{s3_key} --region ap-northeast-1
    """

    response = ec2.run_instances(
        ImageId=AMI_ID,
        InstanceType=instance_type,
        MinCount=1,
        MaxCount=1,
        UserData=user_data_script,
        IamInstanceProfile={"Name": INSTANCE_PROFILE},
    )

    instance_id = response["Instances"][0]["InstanceId"]

    s3_url = f"https://{S3_BUCKET}.s3.ap-northeast-1.amazonaws.com/{s3_key}"
    return {
        "message": f"Instance {instance_id} launched. Result will be uploaded to S3.",
        "instance_id": instance_id,
        "result_url": s3_url
    }


# === 2️⃣ 既存インスタンスの操作 ===
@app.tool()
def start_instance(instance_id: str):
    ec2.start_instances(InstanceIds=[instance_id])
    return {"message": f"Instance {instance_id} is starting..."}

@app.tool()
def stop_instance(instance_id: str):
    ec2.stop_instances(InstanceIds=[instance_id])
    return {"message": f"Instance {instance_id} is stopping..."}

@app.tool()
def terminate_instance(instance_id: str):
    ec2.terminate_instances(InstanceIds=[instance_id])
    return {"message": f"Instance {instance_id} is terminating..."}

@app.tool()
def describe_instance(instance_id: str):
    response = ec2.describe_instances(InstanceIds=[instance_id])
    state = response["Reservations"][0]["Instances"][0]["State"]["Name"]
    return {"instance_id": instance_id, "state": state}


if __name__ == "__main__":
    app.run()
