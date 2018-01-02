#!/usr/bin/python
# -*- coding: utf-8 -*-

import json

import appier

import repos

class PackageController(appier.Controller):

    @appier.route("/packages", "GET", json = True)
    def list(self):
        self.ensure_auth()
        object = appier.get_object(alias = True, find = True)
        packages = repos.Package.find(map = True, **object)
        return packages

    @appier.route("/packages/<str:name>", "GET", json = True)
    def retrieve(self, name):
        self.ensure_auth()
        version = self.field("version")

        # tries to retrieve the value of the current artifact
        # it can be either a local file tuple or remote URL
        result = repos.Artifact.retrieve(
            name = name,
            version = version
        )

        # in case the resulting value is a string it's assumed
        # that it should be an URL and proper redirect is ensured
        if appier.legacy.is_str(result): return self.redirect(result)

        # otherwise the result should be a tuple and we must unpack
        # it to check for proper contents
        data, file_name, content_type = result
        appier.verify(
            not data == None,
            message = "No data available in the package",
            exception = appier.OperationalError
        )
        content_type = content_type or "application/octet-stream"
        return self.send_file(
            data,
            name = file_name,
            content_type = content_type
        )

    @appier.route("/packages", "POST", json = True)
    @appier.ensure(token = "admin")
    def publish(self):
        name = self.field("name", mandatory = True)
        version = self.field("version", mandatory = True)
        contents = self.field("contents")
        url = self.field("url")
        identifier = self.field("identifier")
        info = self.field("info")
        type = self.field("type")
        content_type = self.field("content_type")
        if info: info = json.loads(info)
        if contents: _name, _content_type, data = contents
        else: data = None
        artifact = repos.Artifact.publish(
            name,
            version,
            data = data,
            url = url,
            identifier = identifier,
            info = info,
            type = type,
            content_type = content_type
        )
        return dict(
            key = artifact.key,
            package = artifact.package.name,
            version = artifact.version,
            file_name = artifact.file_name,
            content_type = artifact.content_type
        )

    @appier.route("/packages/<str:name>/info", "GET", json = True)
    def info(self, name):
        self.ensure_auth()
        version = self.field("version")
        return repos.Artifact._info(name = name, version = version)

    def ensure_auth(self):
        username = appier.conf("REPO_USERNAME", None)
        password = appier.conf("REPO_PASSWORD", None)
        if not username: return
        authorization = self.request.authorization
        is_valid = authorization == (username, password)
        if not is_valid: raise appier.SecurityError(
            message = "Authentication failed",
            code = 401,
            headers = {
                "WWW-Authenticate" : "Basic realm=\"default\""
            }
        )
