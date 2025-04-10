import time
import sys
import yaml
import boto3


class Eks:
    def __init__(self, eks_name, region):
        self.eks_name = eks_name
        self.region = region
        self.eks_client = boto3.client('eks', region_name=region)
        self.asg_client = boto3.client('autoscaling', region_name=region)
        self.eks_ngs = self.eks_client.list_nodegroups(clusterName=eks_name).get("nodegroups", [])

    def set_asg_to_zero(self):
        if not self.eks_ngs:
            print(f"Cluster {self.eks_name} has no node groups.")
            return

        print(f"\nStopping node group instances for EKS cluster '{self.eks_name}'")
        for ng in self.eks_ngs:
            try:
                ng_details = self.eks_client.describe_nodegroup(clusterName=self.eks_name, nodegroupName=ng)['nodegroup']
                asg_name = ng_details["resources"]["autoScalingGroups"][0]["name"]
                self.asg_client.delete_tags(
                    Tags=[
                        {
                            'ResourceId': asg_name,
                            'ResourceType': 'auto-scaling-group',
                            'Key': 'k8s.io/cluster-autoscaler/enabled',
                        },
                        {
                            'ResourceId': asg_name,
                            'ResourceType': 'auto-scaling-group',
                            'Key': f'k8s.io/cluster-autoscaler/{self.eks_name}',
                        }
                    ]
                )
            except Exception as e:
                print(f"Failed to remove autoscaler tags for node group '{ng}': {e}")

        print("Autoscaler tags removed. Waiting 60s for cache update...")
        time.sleep(60)

        for ng in self.eks_ngs:
            try:
                self.eks_client.update_nodegroup_config(
                    clusterName=self.eks_name,
                    nodegroupName=ng,
                    scalingConfig={"minSize": 0, "desiredSize": 0}
                )
                print(f"Node group '{ng}' scaled to 0")
            except Exception as e:
                print(f"Failed to scale down node group '{ng}': {e}")

    def set_asg_to_required(self, desired_size=3):
        if not self.eks_ngs:
            print(f"Cluster {self.eks_name} has no node groups.")
            return

        print(f"\n🚀 Starting node group instances for EKS cluster '{self.eks_name}'")
        for ng in self.eks_ngs:
            try:
                ng_details = self.eks_client.describe_nodegroup(clusterName=self.eks_name, nodegroupName=ng)['nodegroup']
                asg_name = ng_details["resources"]["autoScalingGroups"][0]["name"]

                self.asg_client.create_or_update_tags(
                    Tags=[
                        {
                            'ResourceId': asg_name,
                            'ResourceType': 'auto-scaling-group',
                            'Key': 'k8s.io/cluster-autoscaler/enabled',
                            'Value': 'true',
                            'PropagateAtLaunch': True,
                        },
                        {
                            'ResourceId': asg_name,
                            'ResourceType': 'auto-scaling-group',
                            'Key': f'k8s.io/cluster-autoscaler/{self.eks_name}',
                            'Value': 'owned',
                            'PropagateAtLaunch': True,
                        }
                    ]
                )
            except Exception as e:
                print(f"Failed to apply autoscaler tags for '{ng}': {e}")

        for ng in self.eks_ngs:
            try:
                self.eks_client.update_nodegroup_config(
                    clusterName=self.eks_name,
                    nodegroupName=ng,
                    scalingConfig={"minSize": 0, "desiredSize": desired_size}
                )
                print(f"Node group '{ng}' scaled up to {desired_size}")
            except Exception as e:
                print(f"Failed to scale up node group '{ng}': {e}")


def main():
    with open("config.yaml", "r") as f:
        config = yaml.safe_load(f)

    product = sys.argv[1]
    env = sys.argv[2]
    command = sys.argv[3]

    eks_clusters = config["halt"][product][env]["eks"]
    region = config["halt"][product][env]["region"]

    for eks_cluster in eks_clusters:
        eks = Eks(eks_cluster, region)
        if command == "stop":
            eks.set_asg_to_zero()
        elif command == "start":
            eks.set_asg_to_required()
        else:
            print("Invalid command. Use 'start' or 'stop'.")


if __name__ == "__main__":
    main()


