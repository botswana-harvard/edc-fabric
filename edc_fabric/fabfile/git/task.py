import os
import sys

from fabric.api import local, lcd, env, warn, task, abort
from fabric.colors import blue

from ..repositories import get_repo_name


@task
def generate_requirements(source_root=None, project_repo_name=None,
                          requirements_file=None, new_filename=None):
    """For example:
        fab -H localhost common.generate_requirements:source_root=/Users/imosweu/source,project_repo_name=flourish,requirements_file=requirements.txt,new_filename=requirements_production.txt
    """
    source_root = source_root or env.source_root
    project_repo_name = project_repo_name or env.project_repo_name
    requirements_file = requirements_file or env.requirements_file
    new_requirements_file = new_filename or f'{requirements_file.split(".")[0]}.new'
    organizations = [
        'botswana-harvard', 'cancer', 'Botswana-Harvard-Utility-Systems',
                     'cancer-study', 'tshilo-dikotla', 'flourishbhp', 'potlako-plus',
                     'covid19-vaccine']
    with open(os.path.join(source_root, project_repo_name, requirements_file), 'r') as f, open(
            os.path.join(source_root, project_repo_name, new_requirements_file), 'w') as new_file:
        lines = f.read()
        for line in lines.split('\n'):
            if any(org in line for org in organizations):
                repo_url = line.split('@')[0].replace('git+', '')
                repo_name = get_repo_name(repo_url)
                print("??????????????", repo_name)
                with lcd(os.path.join(source_root, repo_name)):
                    current_tag = local(
                        'git describe --tags `git rev-list --tags --max-count=1`', capture=True)
                pre_stub = line.split('@')[0]
                new_file.write(f'{pre_stub}@{current_tag}#egg={repo_name}\n')


@task
def clone_repos(source_root=None, project_repo_name=None, requirements_file=None,
                 organizations=None):
    """
    Clone repos on the local machine for modules listed in
    requirements.

    For example:
        fab -H localhost clone_repos:source_root=/Users/imosweu/source,project_repo_name=flourish,\
        requirements_file=requirements.txt
    """
    source_root = source_root or env.source_root
    project_repo_name = project_repo_name or env.project_repo_name
    requirements_file = requirements_file or env.requirements_file
    organizations = organizations or [
        'botswana-harvard', 'potlako-plus', 'cancer-study', 'tshilo-dikotla',
        'BHP-Pharmacy', 'Botswana-Harvard-Utility-Systems', 'flourishbhp',
        '']

    # clone requirements
    with open(os.path.join(source_root, project_repo_name, requirements_file), 'r') as f:
        lines = f.read()
        for line in lines.split('\n'):
            if any(org in line for org in organizations):
                # project_repo_name in line:
                repo_url = line.split('@')[0].replace('git+https://github.com/', 'git@github.com:')
                repo_name = get_repo_name(repo_url)
                with lcd(source_root):
                    if not os.path.isdir(os.path.join(source_root, repo_name)):
                        sys.stdout.write(f'\n cloning {repo_name}')
                        local(f'git clone {repo_url}')


@task
def cut_releases(source_root=None, project_repo_name=None, requirements_file=None,
                 organizations=None, dry_run=None):
    """
    Cuts releases on the local machine for modules listed in
    requirements.

    For example:
        fab -H localhost common.cut_releases:source_root=/Users/imosweu/source,project_repo_name=flourish,requirements_file=requirements.txt,dry_run=True
    """
    source_root = source_root or env.source_root
    project_repo_name = project_repo_name or env.project_repo_name
    requirements_file = requirements_file or env.requirements_file
    organizations = organizations or [  'botswana-harvard',
                                        # 'potlako-plus',
                                        # 'covid19-vaccine',
                                        'flourishbhp',
                                        # 'BHP-Pharmacy'
                                        ]
    # release project repo.
    # new_release(source_root=source_root,
                # repo_name=project_repo_name, dry_run=dry_run)
    # release requirements
    with open(os.path.join(source_root, project_repo_name, requirements_file), 'r') as f:
        lines = f.read()
        for line in lines.split('\n'):
            if any(org in line for org in organizations):
                # project_repo_name in line:
                repo_url = line.split('@')[0].replace('git+', '')
                repo_name = get_repo_name(repo_url)
                if repo_name:
                    sys.stdout.write(f'\n{line}')
                    new_release(source_root=source_root,
                                repo_name=repo_name, dry_run=dry_run)


def get_next_tag(current_tag=None):
    """
    Returns the next tag.
    """
    tag = current_tag.split('.')
    minor_version = int(tag[-1:][0]) + 1
    tag = tag[:-1]
    tag.append(str(minor_version))
    return '.'.join(tag)


@task
def new_release(source_root=None, repo_name=None, dry_run=None, git_flow_init=None,
                current_tag=None, force_increment=None):
    """Cuts a release for the given repo.

    Tag is incremented as a patch, e.g. 0.1.11 -> 0.1.12

    Example:

        fab -H localhost common.new_release:source_root=/Users/imosweu/source,repo_name=edc-document-archieve-api

    """
    source_root = source_root or env.remote_source_root
    with lcd(os.path.join(source_root, repo_name)):
        print(os.path.join(source_root, repo_name))
        local('git checkout master')
        local('git pull')
        if git_flow_init:
            local('git flow init -d')
        local('git checkout develop')
        local('git pull')
        if not current_tag:
            try:
                current_tag = local(
                    'git describe --tags `git rev-list --tags --max-count=1`', capture=True)
            except:
                current_tag = '0.1.0'
        next_tag = get_next_tag(current_tag)
        result = local('git diff --name-status master..develop', capture=True)
        if not result and not force_increment:
            warn(blue(f'{repo_name}: release {current_tag} is current'))
        else:
            if dry_run:
                print(f'{repo_name}-{current_tag}: git flow release start {next_tag}')
            else:
                version_string_before = f'version=\'{current_tag}\''
                version_string_after = f'version=\'{next_tag}\''
                path = os.path.expanduser(
                    os.path.join(source_root, repo_name, 'setup.py'))
                if not os.path.exists(path):
                    abort(f'{repo_name}: setup.py does not exist. Got {path}')
                data = local('cat setup.py', capture=True)
                if version_string_before not in data:
                    abort(f'{repo_name}: {version_string_before} not found '
                          'in setup.py')
                local(f'git flow release start {next_tag}')
                data = local('cat setup.py', capture=True)
                data = data.replace(version_string_before,
                                    version_string_after)
                local(f'echo "{data}" > setup.py')
                local('git add setup.py')
                local('git commit -m \'bump version\'')
                local(
                    f"git flow release finish -m \'{next_tag}\'")
                local('git push')
                local('git push --tags')
                local('git checkout master')
                local('git push')
                local('git checkout develop')
