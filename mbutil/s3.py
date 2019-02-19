# -*- coding: utf-8 -*-

import re
import logging
import botocore
import boto3
import sys
import os
from shapely import wkt
from shapely.geometry import Polygon
from gatilegrid import getTileGrid

import StringIO
import gzip
from datetime import datetime
from textwrap import dedent
import mimetypes

logger = logging.getLogger(__name__)

mimetypes.init()
mimetypes.add_type('application/x-font-ttf', '.ttf')
mimetypes.add_type('application/x-protobuf', '.pbf')
mimetypes.add_type('application/x-font-opentype', '.otf')
mimetypes.add_type('application/vnd.ms-fontobject', '.eot')
mimetypes.add_type('application/json; charset=utf-8', '.json')
mimetypes.add_type('text/cache-manifest', '.appcache')
mimetypes.add_type('text/plain', '.txt')
mimetypes.add_type('image/png', '.png')
mimetypes.add_type('image/jpeg', '.jpeg')

IS_COMPRESSED = [
	'application/x-protobuf'
]

NO_COMPRESS = [
    'image/jpeg',
    'image/x-icon',
    'image/vnd.microsoft.icon',
    'application/x-font-ttf',
    'application/x-font-opentype',
    'application/vnd.ms-fontobject']


def _gzip_data(data):
    out = None
    infile = StringIO.StringIO()
    try:
        gzip_file = gzip.GzipFile(fileobj=infile, mode='w', compresslevel=5)
        gzip_file.write(data)
        gzip_file.close()
        infile.seek(0)
        out = infile.getvalue()
    except:
        out = None
    finally:
        infile.close()
    return out


def _unzip_data(compressed):
    inbuffer = StringIO.StringIO(compressed)
    f = gzip.GzipFile(mode='rb', fileobj=inbuffer)
    try:
        data = f.read()
    finally:
        f.close()
    return data


def save_to_s3(in_data, dest, bucket_name, compress=True, cached=True):
    mimetype = get_file_mimetype(dest)
    data = in_data
    compressed = False
    content_encoding = None
    cache_control = 'max-age=1800, public'
    extra_args = {}
    

    if compress and mimetype not in NO_COMPRESS:
        data = _gzip_data(in_data)
        compressed = True

    if compress and mimetype in IS_COMPRESSED:
        compressed = True
 
    if compressed == True:
        extra_args['ContentEncoding'] = 'gzip' if compressed is True else None

    if cached is False:
        cache_control = 'max-age=0, must-revalidate, s-maxage=900'

    #extra_args['ACL'] = 'public-read'
    extra_args['ContentType'] = mimetype
    extra_args['CacheControl'] = cache_control
    
    try:
        logger.info('Uploading to %s - %s, gzip: %s, cache headers: %s' % (dest, mimetype, compressed, cached))

        if cached is False:
            extra_args['Expires'] = datetime(1990, 1, 1)
            extra_args['Metadata'] = {'Pragma': 'no-cache', 'Vary': '*'}
        print(dest)
        if not isinstance(data, type(b'')):
          data = _unzip_data(data)
        s3.Object(bucket_name, dest).put(Body=data, **extra_args)
    except Exception as e:
        print('Error while uploading %s: %s' % (dest, e))
        sys.exit(1)

def get_file_mimetype(local_file):
    mimetype, _ = mimetypes.guess_type(local_file)
    if mimetype:
        return mimetype
    return 'text/plain'

'''
def upload(source_dir, bucket_name, s3_dir_path, swissboundaries, grid):
    print('Destionation folder is:')
    print('%s' % s3_dir_path)
    exclude_filename_patterns = ['.less', '.gitignore', '.mako.']
    for file_path_list in os.walk(source_dir):
        file_names = file_path_list[2]
        if len(file_names) > 0:
            file_base_path = file_path_list[0]
            for file_name in file_names:
                if len([p for p in exclude_filename_patterns if p in file_name]) == 0:
                    local_file = os.path.join(file_base_path, file_name)
                    relative_file_path = file_base_path.replace('cache', '')
                    relative_file_path = relative_file_path.replace(source_dir + '/', '')
                    remote_file = os.path.join(s3_dir_path, relative_file_path, file_name)
                    mimetype = get_file_mimetype(local_file)
                    m = re.match('.+\/(\d+)\/(\d+)\/(\d+)\.[a-zA-Z\d]+$', local_file)
                    ignore = False
                    if m is not None and len(m.groups()) == 3:
                        tB = grid.tileBounds(int(m.groups()[0]), int(m.groups()[1]), int(m.groups()[2]))
                        tile = Polygon([(tB[0], tB[1]), (tB[0], tB[3]), (tB[2], tB[3]), (tB[2], tB[1])])
                        if swissboundaries.contains(tile):
                            ignore = True
                    if ignore == False:
                        save_to_s3(local_file, remote_file, bucket_name)

    print 'upload done'
'''

def init_connection(bucket_name, profile_name):
    global s3
    try:
        session = boto3.session.Session(profile_name=profile_name)
    except botocore.exceptions.ProfileNotFound as e:
        print('You need to set PROFILE_NAME to a valid profile name in $HOME/.aws/credentials')
        print(e)
        sys.exit(1)
    except botocore.exceptions.BotoCoreError as e:
        print('Cannot establish connection. Check you credentials %s.' % profile_name)
        print(e)
        sys.exit(1)

    s3client = session.client('s3', config=boto3.session.Config(signature_version='s3v4'))
    s3 = session.resource('s3', config=boto3.session.Config(signature_version='s3v4'))

    bucket = s3.Bucket(bucket_name)
    return (s3, s3client, bucket)

'''
def exit_usage(cmd_type):
    usage()
    print('Missing one arg for %s command' % cmd_type)
    sys.exit(1)


def parse_arguments(argv):
    if len(argv) < 4:
        exit_usage('UNKNOWN')

    source_dir = os.path.abspath(argv[1])
    if not os.path.isdir(source_dir):
        print('Source directory does not exist %s' % source_dir)
        sys.exit(1)

    bucket_name = argv[2]
    if bucket_name is None:
        usage()
        print('%s no bucket name specified')
        sys.exit(1)

    s3_path = None
    s3_path = argv[3]
    if not s3_path.endswith('/'):
        s3_path = s3_path + '/'

    user = os.environ.get('USER')
    profile_name = '{}_aws_admin'.format(user)

    return (source_dir, bucket_name, s3_path, profile_name)


def main():
    source_dir, bucket_name, s3_path, profile_name = parse_arguments(sys.argv)
    init_connection(bucket_name, profile_name)

    with open('./swiss_boundaries_3857.wkt', 'r') as f:
        swissboundaries = wkt.load(f)

    grid = getTileGrid(3857)()

    print('Uploading %s to s3' % source_dir)
    upload(source_dir, bucket_name, s3_path, swissboundaries, grid)

if __name__ == '__main__':
    main()
'''
