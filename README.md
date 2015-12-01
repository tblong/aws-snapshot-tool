aws-snapshot-tool
=================
aws-snapshot-tool is a python script for AWS Lambda to make it easy to *roll snapshot of your EBS volumes*. 

Simply add a tag to each volume you want snapshots of, configure the aws-snapshot-tool config file and you are off. Based of how many snapshots you are wanting to keep and the scheduling you have set for AWS Lambda to execute the AWS Lambda code, it will handle rolling snapshots on any schedule so that you can setup the retention policy to suit.

Features:
- *Python based*: Leverages boto and is easy to configure and upload to AWS Lambda server
- *Simple tag system*: Just add a tag to each of your EBS volumes you want snapshots of
- *Configure retention policy*: Configure how many snapshots you want to retain
- *Optimized for AWS Lambda scheduling*: Allows the scheduling to be set within AWS Lambda not the config file.
- *SNS Notifications*: aws-snapshot-tool works with Amazon SNS out of the box, so you can be notified of snapshots

Usage
==========
1. Create a project folder for all of the projects resources.
2. Install the Boto package, by using pip, inside of the project folder(not Boto3) (See: [Pip_Install](https://pip.pypa.io/en/latest/installing/) [Boto_Install](https://github.com/boto/boto))
3. Place both the snapshots.py and config.sample inside of the project folder
4. Create a SNS topic in AWS and copy the ARN into the config file
5. Subscribe with a email address to the SNS topic
6. Create a snapshot user in IAM and put the key and secret in the config file
7. Create a security policy for this user (see the iam.policy.sample)
8. Copy config.sample to config.py
9. Decide how many versions of the snapshots you want and change this in config.py
10. Change the Region and Endpoint for AWS in the config.py file
11. Optionally specify a proxy if you need to, otherwise set it to '' in the config.py
12. In config.py, specify the tags to give to the snapshot
13. Give every Volume for which you want snapshots a Tag with a Key and a Value and put these in the config file. Default: "autosnap" and the value "true"
14. After completion of configuring config.py, within the project folder, zip up all of the contents as one zip file
15. Upload the zip file within the project folder to AWS Lambda
16. Under the settings within AWS Lambda, configure the scheduling for the snapshots to be taken(see:[Scheduled Events](http://docs.aws.amazon.com/lambda/latest/dg/getting-started-scheduled-events.html)) 

Additional Notes
=========
The user that executes the script needs the following policies: see iam.policy.sample

