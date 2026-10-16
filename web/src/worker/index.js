// holibase.org: www -> apex redirect, everything else is a static file from web/public.
export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.hostname === "www.holibase.org") {
      url.hostname = "holibase.org";
      return Response.redirect(url.toString(), 301);
    }
    return env.ASSETS.fetch(request);
  },
};
