#!/usr/bin/python
# -*- coding: utf-8 -*-

import appier
import appier_extras


class ReposApp(appier.WebApp):

    def __init__(self, *args, **kwargs):
        appier.WebApp.__init__(
            self, name="repos", parts=(appier_extras.AdminPart,), *args, **kwargs
        )

    def _version(self):
        return "0.2.0"

    def _description(self):
        return "Repos"

    def _observations(self):
        return "Modular repository management system"


if __name__ == "__main__":
    app = ReposApp()
    app.serve()
else:
    __path__ = []
