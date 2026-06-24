const path = require("path");

/** @type {import('next').NextConfig} */
const nextConfig = {
  // Scope file tracing to this app. A stray lockfile in a parent directory can
  // otherwise make Next.js infer the wrong workspace root.
  outputFileTracingRoot: path.join(__dirname),
};

module.exports = nextConfig;
