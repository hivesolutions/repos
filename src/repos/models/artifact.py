#!/usr/bin/python
# -*- coding: utf-8 -*-

import os
import time
import shutil
import zipfile
import tempfile

import appier
import appier_extras

from . import package


class Artifact(appier_extras.admin.Base):
    """
    The base unit for the management or a repository, should
    be an concrete based entity belonging to a package.

    It may either manage the storage of the artifact files
    itself or delegate management on a third party.
    """

    key = appier.field(
        index=True,
        immutable=True,
        observations="""Immutable secret key that may be
        used to access the artifact""",
    )
    """ The immutable secret key that may be used to access
    the current artifact with no authentication """

    version = appier.field(
        index=True,
        default=True,
        immutable=True,
        observations="""Simple string identifying the version
        of this artifact should be in the form of x.x.x""",
    )
    """ A simple string identifying the version of this artifact
    should be in the form of "x.x.x", "master", "stable" etc." """

    branch = appier.field(
        index=True,
        initial="master",
        observations="""Name of the branch to which this artifact
        belongs to""",
    )
    """ The name of the branch to which this artifact belongs to,
    by default an artifact belongs to the master branch as this is
    the one tracked by the package to be the latest, other branches
    may exist but explicit request must be used for its retrieval """

    tags = appier.field(
        type=list,
        index=True,
        initial=[],
        observations="""Sequence of tags that describe features
        or characteristics of the artifact""",
    )
    """ A sequence of tags that describe features or characteristics
    of the artifact (eg: stable, production, buggy, etc.) """

    timestamp = appier.field(
        type=int,
        index="all",
        safe=True,
        meta="datetime",
        observations="""The date (and time) of when this artifact
        has been published""",
    )
    """ The date (and time) of when this artifact has been published
    (made available), this should be considered from a practical point
    of view as an immutable field """

    info = appier.field(
        type=dict,
        private=True,
        observations="""Special dictionary that contain meta-information
        about the artifact""",
    )
    """ Dictionary that contains a series of meta-information about
    this artifact (eg: external URLs, description, timestamps, etc.) """

    content_type = appier.field(
        index=True,
        observations="""The MIME based content type of the
        artifact, used in data retrieval""",
    )
    """ The field that describes the MIME based content type of the
    artifact, to be used in data retrieval """

    path = appier.field(
        index=True,
        private=True,
        observations="""File system path to the file where this
        artifact can be found""",
    )
    """ The file system path to the file where this artifact can be
    found, this may be empty if the artifact is an external one """

    url = appier.field(
        index=True,
        private=True,
        description="URL",
        observations="""The URL to the external resource where this
        artifact data is stored, should be used for HTTP redirection""",
    )
    """ The URL to the external resource where this artifact data is
    stored, should be used for HTTP redirection """

    url_tags = appier.field(
        type=dict,
        private=True,
        description="URL Tags",
        observations="""Map that associates a certain tag with
        an URL""",
    )
    """ The map that associates a certain tag with an URL, to be used
    for more precise decisions on which URL to used (eg: CDN usage) """

    package = appier.field(
        type=appier.reference(package.Package, name="name"),
        observations="""Reference to the "parent" package to which
        this artifact belongs to""",
    )
    """ Reference to the "parent" package to which this artifact
    belongs, if this value is not set the artifact is considered
    an "orphan" one """

    @classmethod
    def validate(cls):
        return super(Artifact, cls).validate() + [
            appier.not_null("version"),
            appier.not_empty("version"),
            appier.not_null("branch"),
            appier.not_empty("branch"),
            appier.not_null("package"),
        ]

    @classmethod
    def list_names(cls):
        return ["id", "package", "version", "branch", "timestamp"]

    @classmethod
    def order_name(cls):
        return ["timestamp", -1]

    @classmethod
    def retrieve(cls, identifier=None, name=None, version=None, branch=None, tag=None):
        # creates the dynamic set of keyword arguments taking into
        # account the default named arguments values
        kwargs = dict()
        if name:
            kwargs["package"] = name
        if version:
            kwargs["version"] = version
        if branch:
            kwargs["branch"] = branch

        # retrieves the artifact according to the search criteria and
        # verifies that the artifact is stored locally returning immediately
        # if that's not the case (nothing to be locally retrieved)
        artifact = Artifact.get(rules=False, sort=[("timestamp", -1)], **kwargs)
        if not artifact.is_local:
            return artifact.url_tags[tag] if tag else artifact.url

        # reads the complete set of data contents from the artifact path
        # and then returns the tuple with the content type and file name
        contents = cls.read(artifact.path)
        file_name = artifact.file_name
        content_type = artifact.content_type
        return contents, file_name, content_type

    @classmethod
    def publish(
        cls,
        name,
        version,
        branch="master",
        tags=[],
        data=None,
        url=None,
        url_tags=None,
        identifier=None,
        info=None,
        type="package",
        content_type=None,
        replace=True,
    ):
        url_tags = url_tags or dict()
        artifact = Artifact.get(
            package=name, version=version, branch=branch, raise_e=False
        )
        if artifact and not replace:
            raise appier.OperationalError(message="Duplicated artifact")
        if info:
            info["timestamp"] = int(time.time())
        _package = package.Package.get(name=name, raise_e=False)
        if not _package:
            _package = package.Package(
                name=name, identifier=identifier or name, type=type
            )
            _package.save()
        if data:
            path = cls.store(name, version, data)
        else:
            path = None
        artifact = artifact or Artifact(
            version=version, branch=branch, package=_package
        )
        artifact.tags = tags
        artifact.timestamp = int(time.time())
        artifact.info = info
        artifact.path = path
        artifact.url = url
        artifact.url_tags = url_tags
        artifact.content_type = content_type
        artifact.save()
        return artifact

    @classmethod
    def store(cls, name, version, data):
        repo_path = appier.conf("REPO_PATH", "repo")
        base_path = os.path.join(repo_path, name)
        file_path = os.path.join(base_path, version)
        base_path = os.path.normpath(base_path)
        file_path = os.path.normpath(file_path)
        simple_path = "%s/%s" % (name, version)
        if not os.path.exists(base_path):
            os.makedirs(base_path)
        file = open(file_path, "wb")
        try:
            file.write(data)
        finally:
            file.close()
        return simple_path

    @classmethod
    def read(cls, path):
        repo_path = appier.conf("REPO_PATH", "repo")
        full_path = os.path.join(repo_path, path)
        full_path = os.path.normpath(full_path)
        file = open(full_path, "rb")
        try:
            contents = file.read()
        finally:
            file.close()
        return contents

    @classmethod
    def compress(cls):
        repo_path = appier.conf("REPO_PATH", "repo")
        _zip_handle, zip_path = tempfile.mkstemp()
        zip_file = zipfile.ZipFile(zip_path, mode="w", allowZip64=True)
        try:
            for name, _subdirs, files in os.walk(repo_path):
                relative_name = os.path.relpath(name, repo_path)
                zip_file.write(name, relative_name)
                for filename in files:
                    file_path = os.path.join(name, filename)
                    relative_path = os.path.relpath(file_path, repo_path)
                    zip_file.write(file_path, relative_path)
        finally:
            zip_file.close()
        return zip_path

    @classmethod
    def expand(cls, zip_path, empty=True):
        repo_path = appier.conf("REPO_PATH", "repo")
        exists = os.path.exists(repo_path)
        if empty and exists:
            shutil.rmtree(repo_path)
            exists = False
        if not exists:
            os.makedirs(repo_path)
        zip_file = zipfile.ZipFile(zip_path, mode="r")
        try:
            zip_file.extractall(repo_path)
        finally:
            zip_file.close()

    @classmethod
    @appier.link(name="Compress")
    def compress_url(cls, absolute=False):
        return appier.get_app().url_for("base.compress", absolute=absolute)

    @classmethod
    @appier.operation(
        name="Expand",
        parameters=(
            ("Zip File", "file", "file"),
            ("Empty source", "empty", bool, False),
        ),
    )
    def expand_s(cls, file, empty):
        _file_name, _mime_type, data = file
        _handle, path = tempfile.mkstemp()
        file = open(path, "wb")
        try:
            file.write(data)
        finally:
            file.close()
        cls.expand(path, empty=empty)

    @classmethod
    @appier.operation(
        name="Import File",
        parameters=(
            ("Package", "package", str),
            ("Version", "version", str),
            ("File", "file", "file"),
            ("Type", "type", str, "artifact"),
            ("Replace", "replace", bool, True),
        ),
        factory=True,
    )
    def import_file_s(cls, package, version, file, type="artifact", replace=True):
        return cls.publish(
            package,
            version,
            data=file.read(),
            type=type,
            content_type=file.mime,
            replace=replace,
        )

    @classmethod
    @appier.operation(
        name="Import URL",
        parameters=(
            ("Package", "package", str),
            ("Version", "version", str),
            ("URL", "url", str),
            ("Type", "type", str, "artifact"),
            ("Replace", "replace", bool, True),
        ),
        factory=True,
    )
    def import_url_s(cls, package, version, url, type="artifact", replace=True):
        return cls.publish(package, version, url=url, type=type, replace=replace)

    @classmethod
    def _info(cls, name, version=None):
        kwargs = dict()
        if version:
            kwargs["version"] = version
        artifact = Artifact.get(
            package=name, rules=False, sort=[("timestamp", -1)], **kwargs
        )
        return artifact.info

    def pre_create(self):
        appier_extras.admin.Base.pre_create(self)
        self.key = self.secret()
        self.timestamp = int(time.time())

    def pre_update(self):
        appier_extras.admin.Base.pre_update(self)
        self.timestamp = self.timestamp or int(time.time())

    def post_save(self):
        appier_extras.admin.Base.post_save(self)
        if self.is_master:
            self.package.latest = self.version
        if self.branch and not self.branch in self.package.branches:
            self.package.branches.append(self.branch)
        self.package.save()

    @appier.link(name="Retrieve")
    def retrieve_url(self, absolute=False):
        return appier.get_app().url_for(
            "package.retrieve",
            absolute=absolute,
            name=self.package.name,
            version=self.version,
        )

    @appier.link(
        name="Retrieve Tag",
        parameters=(("Tag", "tag", str),),
    )
    def retrieve_tag_url(self, tag, absolute=False):
        return appier.get_app().url_for(
            "package.retrieve",
            absolute=absolute,
            name=self.package.name,
            version=self.version,
            tag=tag,
        )

    @appier.operation(name="Sync Timestamp")
    def sync_timestamp_s(self):
        self.timestamp = self.created
        self.save()

    @appier.operation(name="Set Branch", parameters=(("Branch", "branch", str),))
    def set_branch_s(self, branch):
        self.branch = branch
        self.save()

    @appier.operation(name="Add Tag", parameters=(("Tag", "tag", str),))
    def add_tag_s(self, tag):
        if tag in self.tags:
            return
        self.tags.append(tag)
        self.save()

    @appier.operation(name="Remove Tag", parameters=(("Tag", "tag", str),))
    def remove_tag_s(self, tag):
        if not tag in self.tags:
            return
        self.tags.remove(tag)
        self.save()

    @appier.operation(
        name="Timestampfix",
    )
    def timestampfix_s(self):
        self.timestamp = int(self.timestamp)
        self.save()

    @property
    def file_name(self):
        return "%s-%s.%s" % (
            self.package.name,
            self.version,
            self.package.type or "artifact",
        )

    @property
    def is_local(self):
        return True if self.path else False

    @property
    def is_master(self):
        return self.branch == "master"
