import os
import argparse
import os


parser = argparse.ArgumentParser(description='write json configuration for ngc')
parser.add_argument('dir', type=str, help='relative path to script to withing visual_mpc directory')

args = parser.parse_args()
job_ids = []
dir = args.dir
for j in job_ids:
    cmd = "cd {}; ngc result download {} &".format(dir, j)
    print(cmd)
    os.system(cmd)
