#!/usr/bin/env node
"use strict";

// increase the libuv threadpool size to 1.5x the number of logical CPUs.
process.env.UV_THREADPOOL_SIZE = process.env.UV_THREADPOOL_SIZE || Math.ceil(Math.max(4, require("os").cpus().length * 1.5));

var path = require("path"),
    util = require("util");

var cors = require("cors"),
    express = require("express"),
    lru = require("lru-cache"),
    morgan = require("morgan"),
    responseTime = require("response-time"),
    tessera = require("tessera"),
    tilelive = require("tilelive-cache")(require("@mapbox/tilelive"), {
      sources: 75
    });

require('@mapbox/tilelive-mapnik').registerProtocols(tilelive);
require('tilelive-raster')(tilelive);
require('tilelive-fieldpapers')(tilelive);

var API_BASE_URL = process.env.API_BASE_URL || "http://fieldpapers.org/",
    CACHE = lru(500),
    SUPPORT = express();

// TODO export these from tessera
SUPPORT.use(express.static(path.join(__dirname, "node_modules", "tessera", "public")));
SUPPORT.use(express.static(path.join(__dirname, "node_modules", "tessera", "bower_components")));

var app = express().disable("x-powered-by");

if (process.env.NODE_ENV !== "production") {
  app.use(morgan("dev"));
}

app.use(responseTime());
app.use(cors());
/*
if (process.env.SENTRY_DSN) {
  var raven = require("raven");

  raven.patchGlobal(function(logged, err) {
    console.log("Uncaught error. Reporting to Sentry and exiting.");
    console.error(err.stack);

    process.exit(1);
  });

  app.use(raven.middleware.express());
}
*/

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

var server = express();

server.use(process.env.PATH_PREFIX || "", app);

server.listen(process.env.PORT || 8080, function() {
  console.log("Listening at http://%s:%d/", this.address().address, this.address().port);
});
