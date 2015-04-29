#!/usr/bin/env node
"use strict";

var path = require("path"),
    util = require("util");

var express = require("express"),
    lru = require("lru-cache"),
    tessera = require("tessera"),
    tilelive = require("tilelive-cache")(require("tilelive"), {
      sources: 100
    });

// TODO use tilelive-modules (see mojodna/tilelive-modules#2)
require("tilelive-mapnik").registerProtocols(tilelive);
require("tilelive-raster")(tilelive);
require("tilelive-fieldpapers")(tilelive);

var API_BASE_URL = process.env.API_BASE_URL || "http://fieldpapers.org/",
    CACHE = lru(500),
    SUPPORT = express();

SUPPORT.use(express.static(path.join(__dirname, "node_modules", "tessera", "public")));
SUPPORT.use(express.static(path.join(__dirname, "node_modules", "tessera", "bower_components")));

var app = express();

app.use("/:type(snapshots|atlases)/:slug", function(req, res, next) {
  var key = [req.params.type, req.params.slug].join("-"),
      route;

  if (!(route = CACHE.get(key))) {
    route = tessera(tilelive, {
      source: util.format("fieldpapers+%s%s/%s", API_BASE_URL, req.params.type, req.params.slug)
    });

    route.use(SUPPORT);

    CACHE.set(key, route);
  }

  return route(req, res, next);
});

app.use("/[^\/]+/", SUPPORT);

app.listen(process.env.PORT || 8080, function() {
  console.log("Listening at http://%s:%d/", this.address().address, this.address().port);
});
