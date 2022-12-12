import configparser
import csv
import os
import re
import time

from pathlib import PurePath

from fabric.api import env, local, run, cd, sudo, task, warn, put
from fabric.colors import red
from fabric.contrib.files import contains, exists, sed
from fabric.contrib.project import rsync_project
from fabric.decorators import serial
from fabric.utils import abort

from .constants import LINUX, MACOSX
from .environment import update_fabric_env, bootstrap_env


@task
def launch_webserver_task(target_os=None):
    """Launch or relaunch the web services as a task.

    Assumes all requirements are already installed.
    """
    if target_os == MACOSX:
        launch_webserver_macosx()
    elif target_os == LINUX:
        launch_webserver_linux()


def launch_webserver():
    """Launch or relaunch the web services.

    Used after all requirements are installed.
    """
    if env.target_os == MACOSX:
        launch_webserver_macosx()
    elif env.target_os == LINUX:
        launch_webserver_linux()


def launch_webserver_linux():
    pass


def launch_webserver_macosx():
    """Launch / Relaunch nginx/gunicorn.
    """
    sudo('launchctl unload -w /System/Library/LaunchDaemons/org.apache.httpd.plist', warn_only=True)
    sudo('launchctl unload -F /Library/LaunchDaemons/nginx.plist', warn_only=True)
    sudo('nginx -s stop', warn_only=True)
    run('launchctl unload -F /Library/LaunchDaemons/gunicorn.plist', warn_only=True)
    run("kill `cat ~/log/gunicorn.pid`", warn_only=True)
    sudo('ps auxww | grep gunicorn | awk \'{print $2}\' | xargs kill -9',
         warn_only=True)
    sudo('launchctl load -F /Library/LaunchDaemons/nginx.plist')
    run('launchctl load -F /Library/LaunchDaemons/gunicorn.plist')
    time.sleep(5)
    run('curl http://localhost')


def put_bash_config():
    if env.target_os == MACOSX:
        bash_config = 'bash_profile'
    elif env.target_os == LINUX:
        bash_config = 'bash_aliases'
    run('rm -rf ~/.bash_*', warn_only=True)
    local_copy = os.path.expanduser(os.path.join(
        env.fabric_config_root, 'conf', bash_config))
    remote_copy = f'~/.{bash_config}'
    put(local_copy, remote_copy)
    result = run(f'source ~/.{bash_config}')
    if result:
        warn(f'{env.host}: {bash_config}. Got {result}')


def check_deviceids(app_name=None):
    """Checks remote device id against conf dictionary.

    Aborts on first error.
    """
    app_name = app_name or env.project_appname
    remote_path = os.path.join(
        env.remote_source_root, env.project_appname, app_name)
    for host, device_id in env.device_ids.items():
        with cd(remote_path):
            if not contains('settings.py', 'DEVICE_ID = {}'.format(device_id)):
                abort(red('{} Incorrect device id. Expected {}.'.format(
                    host, device_id)))
#                 fd = StringIO()
#                 get(os.path.join(remote_path, 'settings.py'), fd)
#                 content = fd.getvalue()
#                 print('content', content)


def get_hosts(path=None, gpg_filename=None):
    """Returns a list of hostnames extracted from the hosts.conf.gpg.

    Does nothing if env.hosts is already set.
    """
    # see also roledefs
    hosts = []
    passwords = {}

    if env.roles:
        for role in env.roles:
            env.hosts.extend(env.roledefs.get(role) or [])
    conf_string = local(f'cd {path}&&gpg --decrypt {gpg_filename}', capture=True)
    conf_string = conf_string.replace(
        'gpg: WARNING: message was not integrity protected', '\n')
    conf_data = conf_string.split('\n')
    csv_reader = csv.reader(conf_data)
    if env.hosts:
        for index, row in enumerate(csv_reader):
            if index == 0:
                continue
            else:
                if row[0] in env.hosts:
                    host = '{user}@{hostname}:22'.format(
                        user=env.user or 'django', hostname=row[0])
                    env.passwords.update({host: row[1]})
    else:

        conf_string = local(f'cd {path}&&gpg --decrypt {gpg_filename}', capture=True)
        conf_string = conf_string.replace(
            'gpg: WARNING: message was not integrity protected', '\n')
        conf_data = conf_string.split('\n')
        csv_reader = csv.reader(conf_data)
        for index, row in enumerate(csv_reader):
            if index == 0:
                continue
            hosts.append(row[0])
            host = '{user}@{hostname}:22'.format(
                user=env.user or 'django', hostname=row[0])
            passwords.update({host: row[1]})
    if env.hosts:
        return (env.hosts, env.passwords)
    else:
        return (hosts, passwords)


def get_device_ids(hostname_pattern=None):
    """Returns a list of device IDS based on the hostnames.

    env.hosts must be set first.
    """
    device_ids = {}
    hostname_pattern = hostname_pattern or env.hostname_pattern
    for hostname in env.hosts:
        if (hostname not in env.roledefs.get('deployment_hosts')
                and hostname not in env.roledefs.get('servers', [])):
            if not re.match(hostname_pattern, hostname):
                warn('Invalid hostname. Cannot determine device ID. Ignoring. Got {hostname}'.format(
                    hostname=hostname))
            else:
                device_ids.update({hostname: hostname[-2:]})
    if len(list(set(device_ids))) != len(device_ids):
        abort('Device ID list not unique.')
    return device_ids


def decrypt_to_config(gpg_filename=None, section=None):
    """Returns a config by decrypting a conf file with a single section.
    """
    section = '[{section}]'.format(section=section)
    conf_string = run('gpg --decrypt {gpg_filename}'.format(
        gpg_filename=gpg_filename))
    conf_string = conf_string.replace(
        'gpg: WARNING: message was not integrity protected', '\n')
    conf_string.split(section)[1]
    config = configparser.RawConfigParser()
    config.read_string('{section}\n{conf_string}\n'.format(
        section=section, conf_string=conf_string.split(section)[1]))
    return config


@task
def test_connection(config_path=None, local_fabric_conf=None, bootstrap_branch=None):
    """
    fab -R testhosts -P deploy.test_connection:config_path=/Users/erikvw/source/bcpp/fabfile/,bootstrap_branch=develop,local_fabric_conf=True --user=django

    After run, look in log_folder
    """

    bootstrap_env(
        path=os.path.expanduser(os.path.join(config_path, 'conf')),
        bootstrap_branch=bootstrap_branch)
    update_fabric_env(use_local_fabric_conf=local_fabric_conf)
    result_os = run('sw_vers -productVersion')
    result_mysql = run('mysql -V', warn_only=True)
    result_nginx = run('nginx -V', warn_only=True)
    with open(os.path.join(env.log_folder, '{host}.txt'.format(host=env.host)), 'a') as f:
        if env.os_version not in result_os:
            warn('{} OSX outdated. Got {}'.format(env.host, result_os))
        f.write('{host} OSX {result}\n'.format(
            host=env.host, result=result_os))
        if env.mysql_version not in result_mysql:
            warn('{} MYSQL outdated. Got {}'.format(env.host, result_mysql))
        f.write('{host} MYSQL {result}\n'.format(
            host=env.host, result=result_mysql))
        if env.nginx_version not in result_nginx:
            warn('{} NGINX outdated. Got {}'.format(env.host, result_nginx))
        f.write('{host} NGINX {result}\n'.format(
            host=env.host, result=result_nginx.split('\n')[0]))


@task
def test_connection2(bootstrap_path=None, local_fabric_conf=None, bootstrap_branch=None):
    """
    fab -R testhosts -P deploy.test_connection2:config_path=/Users/erikvw/source/bcpp/fabfile/,bootstrap_branch=develop,local_fabric_conf=True --user=django
    """

    bootstrap_env(
        path=bootstrap_path,
        bootstrap_branch=bootstrap_branch)
    update_fabric_env(use_local_fabric_conf=local_fabric_conf)
    run('sw_vers -productVersion')


@task
def brew_update(config_path=None, local_fabric_conf=None, bootstrap_branch=None):
    """
    fab -R testhosts -P deploy.brew_update:config_path=/Users/erikvw/source/bcpp/fabfile/,bootstrap_branch=develop,local_fabric_conf=True --user=django
    """

    bootstrap_env(
        path=os.path.expanduser(os.path.join(config_path, 'conf')),
        bootstrap_branch=bootstrap_branch)
    update_fabric_env(use_local_fabric_conf=local_fabric_conf)
    run('sw_vers -productVersion')
    run('brew update')


@task
def ssh_copy_id(bootstrap_path=None, use_local_fabric_conf=None, bootstrap_branch=None):
    """
    Example:
        fab -R testhosts -P deploy.ssh_copy_id:config_path=/Users/erikvw/source/bcpp/fabfile/,bootstrap_branch=develop,local_fabric_conf=True --user=django
    """

    bootstrap_env(
        path=os.path.expanduser(bootstrap_path),
        bootstrap_branch=bootstrap_branch)
    update_fabric_env(use_local_fabric_conf=use_local_fabric_conf)
    pub_key = local('cat ~/.ssh/id_rsa.pub', capture=True)
    with cd('~/.ssh'):
        run('touch authorized_keys')
        result = run('cat authorized_keys', quiet=True)
        if pub_key not in result:
            run('cp authorized_keys authorized_keys.bak')
            run(f'echo {pub_key} >> authorized_keys')


@task
@serial
def touch_host(bootstrap_path=None, use_local_fabric_conf=None, bootstrap_branch=None):
    """
    Example:
        fab -R testhosts -P deploy.touch_host:config_path=/Users/erikvw/source/bcpp/fabfile/,bootstrap_branch=develop,use_local_fabric_conf=True --user=django
    """
    bootstrap_env(
        path=os.path.expanduser(bootstrap_path),
        bootstrap_branch=bootstrap_branch)
    update_fabric_env(use_local_fabric_conf=use_local_fabric_conf)
    with cd('~/.ssh'):
        run('touch authorized_keys')


def rsync_deployment_root():
    remote_path = str(PurePath(env.deployment_root).parent)
    if not exists(remote_path):
        run(f'mkdir -p {remote_path}')
    local_path = os.path.expanduser(env.deployment_root)
    rsync_project(local_dir=local_path, remote_dir=remote_path, delete=True)


def update_settings():
    with cd(os.path.join(env.remote_source_root, env.project_repo_name, env.project_appname)):
        sed('settings.py', 'DEBUG \=.*', 'DEBUG \= False')
        # sed('settings.py', 'ANONYMOUS_ENABLED \=.*',
        #    'ANONYMOUS_ENABLED \= False')


def mount_crypto_keys():
    """Mounts the crypto keys volume.
    """
    with cd(env.etc_dir):
        run('hdiutil attach -stdinpass crypto_keys.dmg')


@task
def move_media_folder_task(bootstrap_path=None, bootstrap_branch=None, use_local_fabric_conf=True):
    """Moves media folder out of the source repo.

    Once off ...
    """
    bootstrap_env(
        path=bootstrap_path,
        filename='bootstrap_client.conf',
        bootstrap_branch=bootstrap_branch)

    update_fabric_env(use_local_fabric_conf=use_local_fabric_conf)
    move_media_folder()


def move_media_folder():
    """Moves media folder out of the source repo.
    """
    old_remote_media = os.path.join(
        env.remote_source_root, env.project_repo_name, 'media')
    if exists(old_remote_media):
        run(
            f'rsync -pthrvz --remove-source-files {old_remote_media} ~/', warn_only=True)
