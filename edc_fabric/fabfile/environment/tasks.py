import configparser
import os

from fabric.api import env, abort, local, warn, run
from fabric.colors import yellow
from fabric.contrib.files import exists

from ..repositories import get_repo_name
from ..constants import LINUX, MACOSX


def bootstrap_env(path=None, filename=None, bootstrap_branch=None, verbose=None):
    """Bootstraps env.
    """
    path = os.path.join(os.path.expanduser(path), filename or 'bootstrap.conf')
    bootstrap_branch = bootstrap_branch or 'master'
    config = configparser.RawConfigParser()
    config.read(os.path.expanduser(path))
    env.deployment_download_dir = config['bootstrap']['deployment_download_dir']
    env.downloads_dir = config['bootstrap']['downloads_dir']
    env.target_os = config['bootstrap']['target_os']
    env.project_repo_url = config['bootstrap']['project_repo_url']
    env.deployment_root = config['bootstrap']['deployment_root']
    env.requirements_file = config['bootstrap']['requirements_file']
    env.project_appname = config['bootstrap']['project_appname']
    env.device_role = config['bootstrap'].get('device_role')
    env.device_id = config['bootstrap'].get('device_id')
    env.fabric_conf = config['bootstrap'].get('fabric_conf', 'fabric.conf')
    env.hosts_conf = 'hosts.conf.gpg'
    env.secrets_conf = 'secrets.conf.gpg'
    env.project_repo_name = get_repo_name(env.project_repo_url)
    env.deployment_database_dir = os.path.join(env.deployment_root, 'database')
    env.deployment_dmg_dir = os.path.join(env.deployment_root, 'dmg')
    env.deployment_pip_dir = os.path.join(env.deployment_root, 'pip')
    env.deployment_brew_dir = os.path.join(env.deployment_root, 'brew')
    env.deployment_download_dir = os.path.join(
        env.deployment_root, 'downloads')
    env.project_repo_root = os.path.join(
        env.deployment_root, env.project_repo_name)
    env.fabric_config_root = os.path.join(env.project_repo_root, 'fabfile')
    env.fabric_config_path = os.path.join(
        env.project_repo_root, 'fabfile', 'conf', env.fabric_conf)
    if bootstrap_branch != 'master':
        warn(yellow('bootstrap read from develop!'))
    # else:
    #    warn(blue('bootstrap read from {bootstrap_branch}'.format(
    #        bootstrap_branch=bootstrap_branch)))


def update_env_secrets(path=None, verbose=None):
    """Reads secrets into env from repo secrets_conf.
    """
    path = os.path.expanduser(path)
    secrets_conf_path = os.path.join(path, 'secrets.conf')
    if verbose:
        print('Reading secrets from {secrets_conf_path}'.format(
            secrets_conf_path=secrets_conf_path))
    if not os.path.exists(secrets_conf_path):
        abort('Not found {secrets_conf_gpg_path}'.format(
            secrets_conf_gpg_path=secrets_conf_path))
    config = configparser.RawConfigParser()
    with open(secrets_conf_path, 'r') as f:
        data = f.read()
    config.read_string(data)
    # for key, value in config['secrets'].items():
        # if verbose:
            # print(key)
        # setattr(env, key, value)


def update_fabric_env(use_local_fabric_conf=None, verbose=None):
    if verbose:
        print('fabric_config_path', os.path.expanduser(env.fabric_config_path))
    config = configparser.RawConfigParser()
    user = env.user
    if use_local_fabric_conf:
        data = local('cat {path}'.format(
            path=os.path.expanduser(env.fabric_config_path)), capture=True)
    else:
        if not exists(env.fabric_config_path):
            abort('Missing config file. Expected {path}'.format(
                path=env.fabric_config_path))
        data = run('cat {path}'.format(
            path=env.fabric_config_path), quiet=True)
    config.read_string(data)
    for key, value in config['default'].items():
        setattr(env, key, value)
    for key, value in config['nginx'].items():
        setattr(env, key, value)
    for key, value in config['mysql'].items():
        setattr(env, key, value)
    for key, value in config['virtualenv'].items():
        setattr(env, key, value)
    for key, value in config['repositories'].items():
        if value.lower() in ['true', 'yes']:
            value = True
        elif value.lower() in ['false', 'no']:
            value = False
        setattr(env, key, value)
    for key, value in config['crypto_fields'].items():
        setattr(env, key, value)
    if env.target_os == LINUX:
        env.python_path = '/usr/bin/'
        env.bash_profile = '~/.bash_aliases'
    elif env.target_os == MACOSX:
        env.python_path = '/usr/local/bin/'
        env.bash_profile = '~/.bash_profile'
        env.dmg_path = env.dmg_path or os.path.join(env.etc_dir)
        # print('dmg_path (updated)', env.dmg_path)
    env.create_env = True
    env.update_requirements = True
    env.update_collectstatic = True
    env.update_collectstatic_js_reverse = True
    if user:
        env.user = user
