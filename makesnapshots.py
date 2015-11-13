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

from boto.ec2.connection import EC2Connection
from boto.ec2.regioninfo import RegionInfo
from boto.ec2.ec2object import TaggedEC2Object
import boto.sns
from datetime import datetime
import time
import sys
import logging
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

# List with snapshots to delete
deletelist = []

# Get connection settings from config.py
aws_access_key = config.connection['aws_access_key']
aws_secret_key = config.connection['aws_secret_key']
ec2_region_name = config.connection['ec2_region_name']
ec2_region_endpoint = config.connection['ec2_region_endpoint']
proxyHost = config.connection.get('proxy_host')
proxyPort = config.connection.get('proxy_port')
sns_arn = config.sns.get('topic')

# Number of snapshots to keep
keep_week = config.snaps['keep_week']
keep_day = config.snaps['keep_day']
keep_month = config.snaps['keep_month']


def read_args():
    global period, date_suffix
    if (len(sys.argv) < 2):
        print('Please add a positional argument: day, week or month.')
        quit()
    else:
        if sys.argv[1] == 'day':
            period = 'day'
            date_suffix = datetime.today().strftime('%a')
        elif sys.argv[1] == 'week':
            period = 'week'
            date_suffix = datetime.today().strftime('%U')
        elif sys.argv[1] == 'month':
            period = 'month'
            date_suffix = datetime.today().strftime('%b')
        else:
            print('Please use the parameter day, week or month')
            quit()
    
def setup_logging():
    global email_message
    logging.basicConfig(filename=config.connection['log_file'], filemode='a', level=logging.INFO)
    start_message = 'Started taking %(period)s snapshots at %(date)s.' % {
        'period': period,
        'date': datetime.today().strftime('%Y-%m-%d %H:%M:%S')
    }
    email_message += start_message + "\n\n"
    logging.info(start_message)
    
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
    # for vol in vols:
    #     print 'found volume: %(volume)s attached to %(att_data)s with name %(instance_name)s' % {
    #         'volume': vol.id,
    #         'att_data': vol.attach_data.instance_id,
    #         'instance_name': get_resource_tags(vol.attach_data.instance_id).get('Name')
    #     }
    
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
            logging.error(error)
            snap_create_message += error + '\n'
            

        
        # TODO create function to handle deleting snapshots
    
        # snapshots = vol.snapshots()
        # deletelist = []
        # for snap in snapshots:
        #     sndesc = snap.snap_description
        #     if (sndesc.startswith('week_snapshot') and period == 'week'):
        #         deletelist.append(snap)
        #     elif (sndesc.startswith('day_snapshot') and period == 'day'):
        #         deletelist.append(snap)
        #     elif (sndesc.startswith('month_snapshot') and period == 'month'):
        #         deletelist.append(snap)
        #     else:
        #         logging.info('     Skipping, not added to deletelist: ' + sndesc)

        # for snap in deletelist:
        #     logging.info(snap)
        #     logging.info(snap.start_time)

        # def date_compare(snap1, snap2):
        #     if snap1.start_time < snap2.start_time:
        #         return -1
        #     elif snap1.start_time == snap2.start_time:
        #         return 0
        #     return 1

        # deletelist.sort(date_compare)
        # if period == 'day':
        #     keep = keep_day
        # elif period == 'week':
        #     keep = keep_week
        # elif period == 'month':
        #     keep = keep_month
        # delta = len(deletelist) - keep
        # for i in range(delta):
        #     del_message = '     Deleting snapshot ' + deletelist[i].snap_description
        #     logging.info(del_message)
        #     deletelist[i].delete()
        #     total_deletes += 1
        # time.sleep(3)
    
def make_snapshot(vol):
    """
    Make a snapshot for the volume provided
    
    returns: true if successful, false othewise
    """
    global total_creates, snap_create_message
    logging.info(vol)
    
    try:
        volume_tags = get_resource_tags(vol.id)
        snap_description = '%(period)s_snapshot--%(ec2_name)s--%(ec2_id)s--%(vol_id)s' % {
            'period': period,
            'ec2_name': get_resource_tags(vol.attach_data.instance_id).get('Name'),
            'ec2_id': vol.attach_data.instance_id,
            'vol_id': vol.id
        }
        
        try:
            current_snap = vol.create_snapshot(snap_description)
            set_resource_tags(current_snap, volume_tags)
            suc_message = 'Snapshot created with snap_description: %s and tags: %s' % (snap_description, str(volume_tags))
            logging.info(suc_message)
            snap_create_message += snap_description + '\n'
            total_creates += 1
            return True
        except Exception, e:
            print "Unexpected error:", sys.exc_info()[0]
            logging.error(e)
            count_errors += 1
            return False
        
    except:
        print "Unexpected error:", sys.exc_info()[0]
        logging.error('Error in processing volume with id: ' + vol.id)
        errmsg += 'Error processing volume id ' + vol.id + '\n'
        count_errors += 1
        return False
        
def remove_old_snapshots(vol):
    """
    TODO
    """
    global snap_delete_message, total_deletes
    pass
        
#
# main entry point
#
read_args()
setup_logging()
make_connections()
volume_handler(find_volumes())

# compose email message
email_message += snap_create_message + '\n' + snap_delete_message

email_message += "\nTotal snapshots created: " + str(total_creates)
email_message += "\nTotal snapshot errors: " + str(count_errors)
email_message += "\nTotal snapshots deleted: " + str(total_deletes) + "\n\n"

email_message += 'Finished making snapshots at %(date)s.' % {
    'date': datetime.today().strftime('%d-%m-%Y %H:%M:%S')
}

print email_message
logging.info(email_message)

# SNS reporting
if sns_arn:
    if errmsg:
        sns.publish(topic=sns_arn, message='Error in processing volumes:\n' + errmsg, subject=config.sns['subject'] + ' / ERROR with AWS Snapshot')
    sns.publish(topic=sns_arn, message=email_message, subject=config.sns['subject'])




# original loop for volumes below for now
# for vol in vols:
#     try:
#         logging.info(vol)
#         volume_tags = get_resource_tags(vol.id)
#         snap_description = '%(period)s_snapshot %(vol_id)s_%(period)s_%(date_suffix)s by snapshot script at %(date)s' % {
#             'period': period,
#             'vol_id': vol.id,
#             'date_suffix': date_suffix,
#             'date': datetime.today().strftime('%d-%m-%Y %H:%M:%S')
#         }
#         try:
#             current_snap = vol.create_snapshot(description)
#             # TODO need to merge custom snap_tags from config with tags_volume
#             set_resource_tags(current_snap, tags_volume)
#             suc_message = 'Snapshot created with description: %s and tags: %s' % (description, str(tags_volume))
#             print '     ' + suc_message
#             logging.info(suc_message)
#             total_creates += 1
#         except Exception, e:
#             print "Unexpected error:", sys.exc_info()[0]
#             logging.error(e)
#             pass

#         snapshots = vol.snapshots()
#         deletelist = []
#         for snap in snapshots:
#             sndesc = snap.description
#             if (sndesc.startswith('week_snapshot') and period == 'week'):
#                 deletelist.append(snap)
#             elif (sndesc.startswith('day_snapshot') and period == 'day'):
#                 deletelist.append(snap)
#             elif (sndesc.startswith('month_snapshot') and period == 'month'):
#                 deletelist.append(snap)
#             else:
#                 logging.info('     Skipping, not added to deletelist: ' + sndesc)

#         for snap in deletelist:
#             logging.info(snap)
#             logging.info(snap.start_time)

#         def date_compare(snap1, snap2):
#             if snap1.start_time < snap2.start_time:
#                 return -1
#             elif snap1.start_time == snap2.start_time:
#                 return 0
#             return 1

#         deletelist.sort(date_compare)
#         if period == 'day':
#             keep = keep_day
#         elif period == 'week':
#             keep = keep_week
#         elif period == 'month':
#             keep = keep_month
#         delta = len(deletelist) - keep
#         for i in range(delta):
#             del_message = '     Deleting snapshot ' + deletelist[i].description
#             logging.info(del_message)
#             deletelist[i].delete()
#             total_deletes += 1
#         time.sleep(3)
#     except:
#         print "Unexpected error:", sys.exc_info()[0]
#         logging.error('Error in processing volume with id: ' + vol.id)
#         errmsg += 'Error in processing volume with id: ' + vol.id
#         count_errors += 1
#     else:
#         count_success += 1



