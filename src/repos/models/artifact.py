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
    """

    key = appier.field(
        index = True,
        immutable = True
    )
    """ The immutable secret key that may be used to access
    the current artifact with no authentication """

    version = appier.field(
        index = True,
        default = True,
        immutable = True
    )
    """ A simple string identifying the version of this artifact
    should be in the form of "x.x.x", "master", "stable" etc." """

    info = appier.field(
        type = dict,
        private = True
    )
    """ Dictionary that contains a series of meta-information about
    this artifact (eg: external URLs, description, timestamps, etc.) """

    content_type = appier.field(
        index = True
    )
    """ The field that describes the MIME based content type of the
    artifact, to be used in data retrieval """

    path = appier.field(
        index = True,
        private = True
    )
    """ The file system path to the file where this artifact can be
    found, this may be empty if the artifact is an external one """

    url = appier.field(
        index = True,
        private = True
    )
    """ The URL to the external resource where this artifact data is
    stored, should be used for HTTP redirection """

    package = appier.field(
        type = appier.reference(
            package.Package,
            name = "name"
        )
    )
    """ Reference to the "parent" package to which this artifact
    belongs, if this value is not set the artifact is considered
    an "orphan" one """

    @classmethod
    def validate(cls):
        return super(Artifact, cls).validate() + [
            appier.not_null("version"),
            appier.not_empty("version"),

            appier.not_null("package")
        ]

    @classmethod
    def list_names(cls):
        return ["id", "package", "version", "created", "modified"]

    @classmethod
    def order_name(cls):
        return ["id", -1]

    @classmethod
    def retrieve(cls, identifier = None, name = None, version = None):
        # creates the dynamic set of keyword arguments taking into
        # account the default named arguments values
        kwargs = dict()
        if name: kwargs["package"] = name
        if version: kwargs["version"] = version

        # retrieves the artifact according to the search criteria and
        # verifies that the artifact is stored locally returning immediately
        # if that's not the case (nothing to be locally retrieved)
        artifact = Artifact.get(rules = False, sort = [("version", -1)], **kwargs)
        if not artifact.is_local: return artifact.url

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
        data = None,
        url = None,
        identifier = None,
        info = None,
        type = "package",
        content_type = None,
        replace = True
    ):
        artifact = Artifact.get(package = name, version = version, raise_e = False)
        if artifact and not replace:
            raise appier.OperationalError(message = "Duplicated artifact")
        if info: info["timestamp"] = time.time()
        _package = package.Package.get(name = name, raise_e = False)
        if not _package:
            _package = package.Package(
                name = name,
                identifier = identifier or name,
                type = type
            )
            _package.save()
        if data: path = cls.store(name, version, data)
        else: path = None
        artifact = artifact or Artifact(
            version = version,
            package = _package
        )
        artifact.info = info
        artifact.path = path
        artifact.url = url
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
        if not os.path.exists(base_path): os.makedirs(base_path)
        file = open(file_path, "wb")
        try: file.write(data)
        finally: file.close()
        return simple_path

    @classmethod
    def read(cls, path):
        repo_path = appier.conf("REPO_PATH", "repo")
        full_path = os.path.join(repo_path, path)
        full_path = os.path.normpath(full_path)
        file = open(full_path, "rb")
        try: contents = file.read()
        finally: file.close()
        return contents

    @classmethod
    def compress(cls):
        repo_path = appier.conf("REPO_PATH", "repo")
        _zip_handle, zip_path = tempfile.mkstemp()
        zip_file = zipfile.ZipFile(zip_path, "w")
        try:
            for name, _subdirs, files in os.walk(repo_path):
                relative_name = os.path.relpath(name, repo_path)
                zip_file.write(name, relative_name)
                for filename in files:
                    file_path = os.path.join(name, filename)
                    relative_path = os.path.relpath(file_path, repo_path)
                    zip_file.write(file_path, relative_path)
        finally: zip_file.close()
        return zip_path

    @classmethod
    def expand(cls, zip_path, empty = True):
        repo_path = appier.conf("REPO_PATH", "repo")
        exists = os.path.exists(repo_path)
        if empty and exists: shutil.rmtree(repo_path); exists = False
        if not exists: os.makedirs(repo_path)
        zip_file = zipfile.ZipFile(zip_path, "r")
        try: zip_file.extractall(repo_path)
        finally: zip_file.close()

    @classmethod
    @appier.link(name = "Compress")
    def compress_url(cls, absolute = False):
        return appier.get_app().url_for(
            "base.compress",
            absolute = absolute
        )

    @classmethod
    @appier.operation(
        name = "Expand",
        parameters = (
            ("Zip File", "file", "file"),
            ("Empty source", "empty", bool, False)
        )
    )
    def expand_s(cls, file, empty):
        _file_name, _mime_type, data = file
        _handle, path = tempfile.mkstemp()
        file = open(path, "wb")
        try: file.write(data)
        finally: file.close()
        cls.expand(path, empty = empty)

    @classmethod
    @appier.operation(
        name = "Import File",
        parameters = (
            ("Package", "package", str),
            ("Version", "version", str),
            ("File", "file", "file"),
            ("Type", "type", str, "artifact"),
            ("Replace", "replace", bool, True)
        ),
        factory = True
    )
    def import_file_s(cls, package, version, file, type = "artifact", replace = True):
        return cls.publish(
            package,
            version,
            data = file.read(),
            type = type,
            content_type = file.mime,
            replace = replace
        )

    @classmethod
    @appier.operation(
        name = "Import URL",
        parameters = (
            ("Package", "package", str),
            ("Version", "version", str),
            ("URL", "url", str),
            ("Type", "type", str, "artifact"),
            ("Replace", "replace", bool, True)
        ),
        factory = True
    )
    def import_url_s(cls, package, version, url, type = "artifact", replace = True):
        return cls.publish(
            package,
            version,
            url = url,
            type = type,
            replace = replace
        )

    @classmethod
    def _info(cls, name, version = None):
        kwargs = dict()
        if version: kwargs["version"] = version
        artifact = Artifact.get(
            package = name,
            rules = False,
            sort = [("version", -1)],
            **kwargs
        )
        return artifact.info

    @appier.link(name = "Retrieve")
    def retrieve_url(self, absolute = False):
        return appier.get_app().url_for(
            "package.retrieve",
            absolute = absolute,
            name = self.package.name,
            version = self.version
        )

    @property
    def file_name(self):
        return "%s-%s.%s" % (
            self.package.name,
            self.version,
            self.package.type or "artifact"
        )

    @property
    def is_local(self):
        return True if self.path else False
