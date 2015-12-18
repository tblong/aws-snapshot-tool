#!/usr/bin/env python
#
# (c) 2012/2014 E.M. van Nuil / Oblivion b.v.
#
# makesnapshots.py version 3.3
#
# Changelog
# version 1:   Initial version
# version 1.1: Added snap_description and region
# version 1.2: Added extra error handeling and logging
# version 1.3: Added SNS email functionality for succes and error reporting
# version 1.3.1: Fixed the SNS and IAM problem
# version 1.4: Moved all settings to config file
# version 1.5: Select volumes for snapshotting depending on Tag and not from config file
# version 1.5.1: Added proxyHost and proxyPort to config and connect
# version 1.6: Public release
# version 2.0: Added daily, weekly and montly retention
# version 3.0: Rewrote deleting functions, changed snap_description
# version 3.1: Fix a bug with the deletelist and added a pause in the volume loop
# version 3.2: Tags of the volume are placed on the new snapshot
# version 3.3: Merged IAM role addidtion from Github
# version 4.0: Major restructure, improved tag handling
# version 5.0: recoding to be able to run via AWS Lambda

from boto.ec2.connection import EC2Connection
from boto.ec2.regioninfo import RegionInfo
from boto.ec2.ec2object import TaggedEC2Object
import boto.sns
from datetime import datetime
import sys
import config

# Messages to publish to SNS
email_message = ""
snap_create_message = ""
snap_delete_message = ""
errmsg = ""

# Counters
total_creates = 0
total_deletes = 0
count_errors = 0

# Get connection settings from config.py
aws_access_key = config.connection['aws_access_key']
aws_secret_key = config.connection['aws_secret_key']
ec2_region_name = config.connection['ec2_region_name']
ec2_region_endpoint = config.connection['ec2_region_endpoint']
proxyHost = config.connection.get('proxy_host')
proxyPort = config.connection.get('proxy_port')
sns_arn = config.sns.get('topic')

# Number of snapshots to keep
KEEP_NUM_SNAPS = config.snaps['keep_number_snaps']

def setup_logging():
    global email_message
    start_message = 'Started taking snapshots at %(date)s.' % {
        'date': datetime.today().strftime('%Y-%m-%d %H:%M:%S')
    }
    email_message += start_message + "\n\n"

def make_connections():
    global conn, sns
    region = RegionInfo(name=ec2_region_name, endpoint=ec2_region_endpoint)
    # Connect to AWS using the credentials provided above or in Environment vars or using IAM role.
    print 'Connecting to AWS'
    if proxyHost:
        # proxy:
        # using roles
        if aws_access_key:
            conn = EC2Connection(aws_access_key, aws_secret_key, region=region, proxy=proxyHost, proxy_port=proxyPort)
        else:
            conn = EC2Connection(region=region, proxy=proxyHost, proxy_port=proxyPort)
    else:
        # non proxy:
        # using roles
        if aws_access_key:
            conn = EC2Connection(aws_access_key, aws_secret_key, region=region)
        else:
            conn = EC2Connection(region=region)
    
    # Connect to SNS
    if sns_arn:
        print 'Connecting to SNS'
        if proxyHost:
            # proxy:
            # using roles:
            if aws_access_key:
                sns = boto.sns.connect_to_region(ec2_region_name, aws_access_key_id=aws_access_key, aws_secret_access_key=aws_secret_key, proxy=proxyHost, proxy_port=proxyPort)
            else:
                sns = boto.sns.connect_to_region(ec2_region_name, proxy=proxyHost, proxy_port=proxyPort)
        else:
            # non proxy:
            # using roles
            if aws_access_key:
                sns = boto.sns.connect_to_region(ec2_region_name, aws_access_key_id=aws_access_key, aws_secret_access_key=aws_secret_key)
            else:
                sns = boto.sns.connect_to_region(ec2_region_name)
        
def get_resource_tags(resource_id):
    resource_tags = {}
    if resource_id:
        tags = conn.get_all_tags({'resource-id': resource_id})
        for tag in tags:
            # Tags starting with 'aws:' are reserved for internal use
            if not tag.name.startswith('aws:'):
                resource_tags[tag.name] = tag.value
    return resource_tags

def set_resource_tags(resource, tags):
    """
    Adds tags to a given resource
    
    :type resource: boto.ec2.ec2object.TaggedEC2Object
    :param resource: the resource to add tags to
    
    :type tags: dict
    :param tags: the tags to add to the given resource
    """
    if None in (resource, tags) or not isinstance(resource, TaggedEC2Object):
        return
        
    resource.add_tags(tags)

def find_volumes():
    """
    Get all the volumes that match the filter criteria in config
    
    returns: a list of volumes found
    """
    global email_message
    email_message += 'Finding volumes that match the requested filter: %(filter)s\n\n' % {
        'filter': config.volumes['filter']
    }
    return conn.get_all_volumes(filters=config.volumes['filter'])

def date_compare(snap1, snap2):
    """
    Organizes snapshots by their start_time property
    """
    if snap1.start_time < snap2.start_time:
        return -1
    elif snap1.start_time == snap2.start_time:
        return 0
    return 1

def volume_handler(vols):
    """
    Handles making and removing old snapshots for the given list of volumes.
    If unable to successfully make a snapshot from a volume, a volume's assocaited snapshots
    will not be called for removal based upon the assigned keep policy.
    """
    global snap_create_message, snap_delete_message
    snap_create_message = "List of snapshots created:\n"
    snap_delete_message = "List of snapshots deleted:\n"
    
    for vol in vols:
        successful = make_snapshot(vol)
        if successful:
            remove_old_snapshots(vol)
        else:
            error = 'Error processing volume id ' + vol.id
            snap_create_message += error + '\n'

def make_snapshot(vol):
    """
    Make a snapshot for the volume provided
    
    returns: true if successful, false otherwise
    """
    global total_creates, snap_create_message, count_errors, errmsg
    
    try:
        volume_tags = get_resource_tags(vol.id)
        snap_description = 'snapshot--%(ec2_name)s--%(ec2_id)s--%(vol_id)s' % {
            'ec2_name': get_resource_tags(vol.attach_data.instance_id).get('Name'),
            'ec2_id': vol.attach_data.instance_id,
            'vol_id': vol.id
        }
        
        try:
            current_snap = vol.create_snapshot(snap_description)
            set_resource_tags(current_snap, volume_tags)
            snap_create_message += snap_description + '\n'
            total_creates += 1
            return True
        except Exception:
            print "Unexpected error:", sys.exc_info()[0]
            count_errors += 1
            return False
        
    except:
        print "Unexpected error:", sys.exc_info()[0]
        errmsg += 'Error processing volume id ' + vol.id + '\n'
        count_errors += 1
        return False

def remove_old_snapshots(vol):
    """
    Remove snapshots for the volume provided based upon the keep policy
    """
    global snap_delete_message, total_deletes
    
    snapshots = vol.snapshots()
    deletelist = []
    for snap in snapshots:
        snap_desc = snap.description
        if snap_desc.startswith('snapshot'):
            deletelist.append(snap)
    deletelist.sort(date_compare)

    delta = len(deletelist) - KEEP_NUM_SNAPS
    for i in range(delta):
        snap = deletelist[i]
        snap_delete_message += snap.description + ' start_time=' + snap.start_time + '\n'
        snap.delete()
        total_deletes += 1
        
#
# main entry point
#


def lambda_handler(event, context):
    global email_message, snap_create_message,snap_delete_message, \
        errmsg, total_creates, total_deletes, count_errors

    email_message = ""
    snap_create_message = ""
    snap_delete_message = ""
    errmsg = ""

    # Counters
    total_creates = 0
    total_deletes = 0
    count_errors = 0


    setup_logging()
    make_connections()
    volume_handler(find_volumes())

    # compose email message
    email_message += snap_create_message + '\n' + snap_delete_message

    email_message += "\nTotal snapshots created: " + str(total_creates)
    email_message += "\nTotal snapshot errors: " + str(count_errors)
    email_message += "\nTotal snapshots deleted: " + str(total_deletes) + "\n\n"

    email_message += 'Finished making snapshots at %(date)s.' % {
        'date': datetime.today().strftime('%Y-%m-%d %H:%M:%S')

    }

    print email_message

    # SNS reporting
    if sns_arn:
        if errmsg:
            sns.publish(topic=sns_arn, message='Error in processing volumes:\n' + errmsg, subject=config.sns['subject'] + ' / ERROR with AWS Snapshot')
        sns.publish(topic=sns_arn, message=email_message, subject=config.sns['subject'])
