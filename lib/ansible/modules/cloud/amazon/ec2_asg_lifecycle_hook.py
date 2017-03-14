#!/usr/bin/python
# This file is part of Ansible
#
# Ansible is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Ansible is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Ansible.  If not, see <http://www.gnu.org/licenses/>.
ANSIBLE_METADATA = {'status': ['preview'],
                    'supported_by': 'community',
                    'version': '1.0'}

DOCUMENTATION = """
---
module: ec2_asg_lifecycle_hook
short_description: Create, delete or update AWS ASG Lifecycle Hooks.
description:
  - Can create, delete or update Lifecycle Hooks for AWS Autoscaling Groups.
author: "Igor (Tsigankov) Eyrich (@tsiganenok) <tsiganenok@gmail.com>"
options:
  state:
    description:
      - Create or delete Lifecycle Hook. Present updates existing one or creates if not found.
    required: false
    choices: ['present', 'absent']
    default: present
  lifecycle_hook_name:
    description:
      - The name of the lifecycle hook.
    required: true
  autoscaling_group_name:
    description:
      - The name of the Auto Scaling group to which you want to assign the lifecycle hook.
    required: true
  transition:
    description:
      - The instance state to which you want to attach the lifecycle hook.
    required: true
    choices: ['autoscaling:EC2_INSTANCE_TERMINATING', 'autoscaling:EC2_INSTANCE_LAUNCHING']
  role_arn:
    description:
      - The ARN of the IAM role that allows the Auto Scaling group to publish to the specified notification target.
    required: false
  notification_target_arn:
    description:
      - The ARN of the notification target that Auto Scaling will use to notify you when an
        instance is in the transition state for the lifecycle hook.
        This target can be either an SQS queue or an SNS topic. If you specify an empty string,
        this overrides the current ARN.
    required: false
  notification_meta_data:
    description:
      - Contains additional information that you want to include any time Auto Scaling sends a message to the notification target.
    required: false
  heartbeat_timeout:
    description:
      - The amount of time, in seconds, that can elapse before the lifecycle hook times out.
        When the lifecycle hook times out, Auto Scaling performs the default action.
        You can prevent the lifecycle hook from timing out by calling RecordLifecycleActionHeartbeat.
    required: false
    default: 3600 (1 hour)
  default_result:
    description:
      - Defines the action the Auto Scaling group should take when the lifecycle hook timeout
        elapses or if an unexpected failure occurs. This parameter can be either CONTINUE or ABANDON.
    required: false
    choices: ['ABANDON', 'CONTINUE']
    default: ABANDON
extends_documentation_fragment:
    - aws
    - ec2
requirements: [ boto3>=1.4.4 ]

"""

EXAMPLES = '''
# Create / Update lifecycle hook
- ec2_asg_lifecycle_hook:
    region: eu-central-1
    state: present
    autoscaling_group_name: example
    lifecycle_hook_name: example
    transition: autoscaling:EC2_INSTANCE_LAUNCHING
    heartbeat_timeout: 7000
    default_result: ABANDON

# Delete lifecycle hook
- ec2_asg_lifecycle_hook:
    region: eu-central-1
    state: absent
    autoscaling_group_name: example
    lifecycle_hook_name: example

'''

from ansible.module_utils.basic import *
from ansible.module_utils.ec2 import *

try:
    import boto3
    import botocore
    HAS_BOTO3 = True
except ImportError:
    HAS_BOTO3 = False

def create_lifecycle_hook(connection, module):
    changed = False

    lch_name = module.params.get('lifecycle_hook_name')
    asg_name = module.params.get('autoscaling_group_name')
    transition = module.params.get('transition')
    role_arn = module.params.get('role_arn')
    notification_target_arn = module.params.get('notification_target_arn')
    notification_meta_data = module.params.get('notification_meta_data')
    heartbeat_timeout = module.params.get('heartbeat_timeout')
    default_result = module.params.get('default_result')

    lch_params = {
        'LifecycleHookName': lch_name,
        'AutoScalingGroupName': asg_name,
        'LifecycleTransition': transition
    }

    if role_arn:
        lch_params['RoleARN'] = role_arn

    if notification_target_arn:
        lch_params['NotificationTargetARN'] = notification_target_arn

    if notification_meta_data:
        lch_params['NotificationMetadata'] = notification_meta_data

    if heartbeat_timeout:
        lch_params['HeartbeatTimeout'] = heartbeat_timeout

    if default_result:
        lch_params['DefaultResult'] = default_result

    existing_hook = connection.describe_lifecycle_hooks(
        AutoScalingGroupName=asg_name,
        LifecycleHookNames=[ lch_name ]
    )['LifecycleHooks']

    if not existing_hook:
        changed = True
    else:
        # GlobalTimeout is not configurable, but exists in response.
        # Removing it helps to compare both dicts in order to understand
        # what changes were done.
        del(existing_hook[0]['GlobalTimeout'])
        added, removed, modified, same = dict_compare(lch_params, existing_hook[0])
        if added or removed or modified:
            changed = True

    if changed:
        try:
            connection.put_lifecycle_hook( **lch_params )
        except Exception as e:
            module.fail_json(msg="Failed to create LifecycleHook %s" % str(e), exception=traceback.format_exc(e))

    return(changed)

# stolen from: http://stackoverflow.com/questions/4527942/comparing-two-dictionaries-in-python
# thank you Daniel
def dict_compare(d1, d2):
    d1_keys = set(d1.keys())
    d2_keys = set(d2.keys())
    intersect_keys = d1_keys.intersection(d2_keys)
    added = d1_keys - d2_keys
    removed = d2_keys - d1_keys
    modified = {o : (d1[o], d2[o]) for o in intersect_keys if d1[o] != d2[o]}
    same = set(o for o in intersect_keys if d1[o] == d2[o])
    return added, removed, modified, same

def delete_lifecycle_hook(connection, module):
    changed = False

    lch_name = module.params.get('lifecycle_hook_name')
    asg_name = module.params.get('autoscaling_group_name')

    all_hooks = connection.describe_lifecycle_hooks(
        AutoScalingGroupName=asg_name
    )

    for hook in all_hooks['LifecycleHooks']:
        if hook['LifecycleHookName'] == lch_name:
            lch_params = {
                'LifecycleHookName': lch_name,
                'AutoScalingGroupName': asg_name
            }

            try:
                connection.delete_lifecycle_hook( **lch_params )
                changed = True
            except Exception as e:
                module.fail_json(msg="Failed to delete LifecycleHook %s" % str(e), exception=traceback.format_exc(e))
        else:
            pass

    return(changed)

def main():
    argument_spec = ec2_argument_spec()
    argument_spec.update(
        dict(
            autoscaling_group_name=dict(required=True, type='str'),
            lifecycle_hook_name=dict(required=True, type='str'),
            transition=dict(type='str', choices=['autoscaling:EC2_INSTANCE_TERMINATING', 'autoscaling:EC2_INSTANCE_LAUNCHING']),
            role_arn=dict(type='str'),
            notification_target_arn=dict(type='str'),
            notification_meta_data=dict(type='str'),
            heartbeat_timeout=dict(type='int'),
            default_result=dict(default='ABANDON', choices=['ABANDON', 'CONTINUE']),
            state=dict(default='present', choices=['present', 'absent'])
        )
    )

    module = AnsibleModule(argument_spec=argument_spec)
    state = module.params.get('state')

    if not HAS_BOTO3:
        module.fail_json(msg='boto3 is required for this module')

    region, ec2_url, aws_connect_params = get_aws_connection_info(module, boto3=True)

    if not region:
        module.fail_json(msg="region parameter is required")

    try:
        connection = boto3_conn(module, conn_type='client', resource='autoscaling', region=region, endpoint=ec2_url, **aws_connect_params)
        if not connection:
            module.fail_json(msg="failed to connect to AWS for the given region: %s" % str(region))
    except boto.exception.NoAuthHandlerFound as e:
        module.fail_json(msg=str(e))

    changed = create_changed = replace_changed = False

    if state == 'present':
        if not module.params.get('transition'):
            module.fail_json(msg="transition parameter is required")

        changed = create_lifecycle_hook(connection, module)
    elif state == 'absent':
        changed = delete_lifecycle_hook(connection, module)

    module.exit_json( changed = changed)

if __name__ == '__main__':
    main()
