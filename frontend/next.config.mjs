/** @type {import('next').NextConfig} */
const nextConfig = {
  // Static export so the whole UI can be bundled into the desktop app and served
  // by FastAPI (same origin as /api). `next dev` (web/dev setup) ignores it.
  output: "export",
  trailingSlash: true,        // /wp -> /wp/index.html, easy to serve as static files
  images: { unoptimized: true },
};

export default nextConfig;
