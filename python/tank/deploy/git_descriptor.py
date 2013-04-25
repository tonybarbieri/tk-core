"""
Copyright (c) 2012 Shotgun Software, Inc
----------------------------------------------------

This git descriptor is for a formal git workflow.
It will base version numbering off tags in git.
"""

import os
import copy
import uuid
import tempfile
import subprocess

from .util import subprocess_check_output
from ..api import Tank
from ..errors import TankError
from ..platform import constants
from .descriptor import AppDescriptor
from .zipfilehelper import unzip_file

LATEST = "latest"

class TankGitDescriptor(AppDescriptor):
    """
    Represents a repository in git. New versions are represented by new tags.

    path can be on the form:
    git@github.com:manneohrstrom/tk-hiero-publish.git
    https://github.com/manneohrstrom/tk-hiero-publish.git
    git://github.com/manneohrstrom/tk-hiero-publish.git
    /full/path/to/local/repo.git
    """

    def __init__(self, project_root, location_dict, type):
        super(TankGitDescriptor, self).__init__(project_root, location_dict)

        self._type = type
        self._tk = Tank(project_root)
        self._path = location_dict.get("path")
        self._version = location_dict.get("version")
        self._branch = location_dict.get("branch", "master")
        self._needs_update = location_dict.get("needs_update", False)

        if self._path is None or self._version is None:
            raise TankError("Git descriptor is not valid: %s" % str(location_dict))


    def get_system_name(self):
        """
        Returns a short name, suitable for use in configuration files
        and for folders on disk
        """
        return os.path.basename(self._path)

    def get_version(self):
        """
        Returns the version number string for this item
        """
        return self._version

    def get_path(self):
        """
        returns the path to the folder where this item resides
        """
        # git@github.com:manneohrstrom/tk-hiero-publish.git -> tk-hiero-publish
        # /full/path/to/local/repo.git -> repo.git
        name = os.path.basename(self._path)
        return self._get_local_location(self._type, "git", name, self._version)

    def exists_local(self):
        """
        Returns true if this item exists in a local repo
        """
        if self._needs_update:
            return False
        return os.path.exists(self.get_path())

    def download_local(self):
        """
        Retrieves this version to local repo.
        Will exit early if app already exists local.
        """
        if self.exists_local():
            return
        elif self._needs_update:
            # if using "live mode" perform a git pull for latest.
            #
            # Make sure version is set to latest
            orig_version = self._version
            self._version = "latest"
            self._pull_latest()
            self._needs_update = False
            self._version = orig_version
            return

        target = self.get_path()
        if not os.path.exists(target):
            old_umask = os.umask(0)
            os.makedirs(target, 0777)
            os.umask(old_umask)

        cwd = os.getcwd()
        if self._version == LATEST:
            try:
                os.chdir(os.path.dirname(target))
                if os.system('git clone -q "%s" %s'%(self._path, os.path.basename(target))) != 0:
                    raise TankError("Could not clone git repository '%s'!" % self._path)
                if self._branch != "master":
                    os.chdir(target)
                    if os.system('git checkout -q %s'%(self._branch)) != 0:
                        raise TankError("Could not checkout git branch '%s'!" % self._branch)
            finally:
                os.chdir(cwd)
            return

        # now first clone the repo into a tmp location
        # then zip up the tag we are looking for
        # finally, move that zip file into the target location
        zip_tmp = os.path.join(tempfile.gettempdir(), "%s_tank.zip" % uuid.uuid4().hex)
        clone_tmp = os.path.join(tempfile.gettempdir(), "%s_tank_clone" % uuid.uuid4().hex)
        old_umask = os.umask(0)
        os.makedirs(clone_tmp, 0777)
        os.umask(old_umask)

        # now clone and archive

        try:
            # Note: git doesn't like paths in single quotes when running on windows!
            if os.system("git clone -q \"%s\" %s" % (self._path, clone_tmp)) != 0:
                raise TankError("Could not clone git repository '%s'!" % self._path)

            os.chdir(clone_tmp)

            if os.system("git archive --format zip --output %s %s" % (zip_tmp, self._version)) != 0:
                raise TankError("Could not find tag %s in git repository %s!" % (self._version, self._path))
        finally:
            os.chdir(cwd)

        # unzip core zip file to app target location
        unzip_file(zip_tmp, target)

    def _pull_latest(self):
        """
        Pulls the latest changes from remote.

        If local modifications exist the pull will abort.
        """
        cwd = os.getcwd()
        try:
            os.chdir(self.get_path())
            # First check for any locally modified files before trying to update.
            #
            modified_files = subprocess_check_output("git diff --name-only", shell=True).strip().split("\n")
            if len(modified_files):
                raise TankError("Could not update git repository do to local modifications '%s'!" % self._path)

            if os.system("git pull -q --rebase") != 0:
                raise TankError("Could not update git repository '%s'!" % self._path)

            # Need to check if everything went smoothly or needs to be merged.  If it needs to be merged
            # we should probably abort and have the user update manually...We could also offer to run
            # the merge right then in the command shell?
            #
        finally:
            os.chdir(cwd)

    def find_latest_version(self):
        """
        Returns a descriptor object that represents the latest version
        """

        # now first clone the repo into a tmp location
        clone_tmp = os.path.join(tempfile.gettempdir(), "%s_tank_clone" % uuid.uuid4().hex)
        old_umask = os.umask(0)
        os.makedirs(clone_tmp, 0777)
        os.umask(old_umask)

        # get the most recent tag hash
        cwd = os.getcwd()
        try:
            # Note: git doesn't like paths in single quotes when running on windows!
            if os.system("git clone -q \"%s\" %s" % (self._path, clone_tmp)) != 0:
                raise TankError("Could not clone git repository '%s'!" % self._path)

            os.chdir(clone_tmp)

            needs_update = False
            latest_version = self._version

            if self._version == LATEST:
                # If version is set to latest we are using a live git clone.
                # Check the new clone latest revision for the branch vs the
                # current revision.
                #
                try:
                    if os.system("git checkout -q %s"%self._branch) != 0:
                        raise TankError("Could not checkout branch %s" % (self._branch))
                    git_hash = subprocess_check_output("git rev-list --max-count=1 %s" % self._branch, shell=True).strip()
                except Exception, e:
                    raise TankError("Could not get list of tags for %s: %s" % (self._path, e))

                try:
                    current_git_hash = subprocess_check_output("git rev-list --max-count=1 %s" % self._branch, shell=True).strip()
                except:
                    raise TankError("Could not get current hash for %s: %s" % (self._path, e))

                if current_git_hash != git_hash:
                    latest_version = git_hash[:7]
                    needs_update = True
            else:
                try:
                    git_hash = subprocess_check_output("git rev-list --tags --max-count=1", shell=True).strip()
                except Exception, e:
                    raise TankError("Could not get list of tags for %s: %s" % (self._path, e))

                try:
                    latest_version = subprocess_check_output("git describe --tags %s" % git_hash, shell=True).strip()
                except Exception, e:
                    raise TankError("Could not get tag for hash %s: %s" % (hash, e))

        finally:
            os.chdir(cwd)

        new_loc_dict = copy.deepcopy(self._location_dict)
        new_loc_dict["version"] = latest_version

        # Used in the case of a "live" git repo.
        #
        new_loc_dict["needs_update"] = needs_update

        return TankGitDescriptor(self._pipeline_config, new_loc_dict, self._type)
