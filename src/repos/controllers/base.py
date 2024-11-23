#!/usr/bin/python
# -*- coding: utf-8 -*-

import appier

import repos


class BaseController(appier.Controller):

    @appier.route("/compress", "GET", json=True)
    @appier.ensure(token="admin")
    def compress(self):
        path = repos.Artifact.compress()
        return self.send_path(path, cache=True)
