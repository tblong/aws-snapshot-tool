aws-snapshot-tool
=================
aws-snapshot-tool is a python script for AWS Lambda to make it easy to *roll snapshot of your EBS volumes*. 

Simply assign a tag for each volume that is to have snapshots, configure the aws-snapshot-tool `config.sample` and the AWS Lambda script is ready. Based of how many snapshots that is needed to keep and scheduling that is desired for AWS Lambda to execute the AWS Lambda code, it will handle rolling snapshots on any schedule so that setting up the retention policy is simple.

Features:
- *Python based*: Leverages boto and is easy to configure and upload to AWS Lambda server
- *Simple tag system*: Just add a tag to every EBS volume that need snapshots
- *Configure retention policy*: Configure how many snapshots you want to retain
- *Optimized for AWS Lambda scheduling*: Allows the scheduling to be set within AWS Lambda not the `config.py` file.
- *SNS Notifications*: aws-snapshot-tool works with Amazon SNS out of the box, so notification of snapshots is available 

Usage
==========
1. Create a project folder for all of the projects resources.
2. Install the Boto package, by using pip, inside of the project folder(not Boto3) (see: [Install:Pip](https://pip.pypa.io/en/latest/installing/) [Install:Boto](https://github.com/boto/boto))
3. Place both the `snapshots.py` and `config.sample` inside of the project folder
4. Rename `config.sample` file to `config.py`
5. Create a SNS topic in AWS and copy the ARN into the `config.py` file
6. Subscribe with a email address to the SNS topic to receive updates
7. Create a snapshot user in IAM and put the key and secret in the `config.py` file
8. Create a security policy for this user (see:  [Policy Example](https://github.com/tblong/aws-snapshot-tool/blob/aws-lambda-mods/iam.policy.sample))
9. Decide how many versions of the snapshots you want and change this in the `config.py` file
10. Change the Region and Endpoint for AWS in the `config.py` file
11. Optionally specify a proxy if needed, otherwise set it to '' in the `config.py` file
12. In the `config.py`file, specify the tags that are used to search Volumes and take snapshots
13. For each Volume that is to have snapshots, give a Tag with a Key and a Value, and put this data in the `config.py` file. Default: "autosnap" and the value "true" and "Customer" and the value "Customer Name"
14. Upon completion of configuring `config.py`, within the project folder, zip up all of the contents(`makesnapshots.py`, `config.py`, boto folder, and boto-2.38.0.dist-info folder) as one zip file
15. Upload the zip file within the project folder to AWS Lambda
16. Under the settings within AWS Lambda, configure the scheduling for the snapshots to be taken(see:[Scheduled Events](http://docs.aws.amazon.com/lambda/latest/dg/getting-started-scheduled-events.html)) 

Additional Notes
=========
The user that executes the script needs the following policies: see iam.policy.sample<br />
This script is compatible with Boto, not Boto3<br />
During step 14, the folder "boto-2.38.0.dist-info" may be a different version<br />

