# The landing page

The site is live at **[mirror-worlds.netlify.app](https://mirror-worlds.netlify.app/)**, deployed on Netlify from this repository’s `main` branch. The base directory is the repository root; keep it empty in Netlify’s build settings, rather than setting it to `site/`.

## Preview locally

From this repository, with Python 3 installed:

```sh
python scripts/build_site.py
python -m http.server 8794 --directory .site-build
```

Open **http://localhost:8794**. The website uses ordinary HTML, CSS and JavaScript; it needs no npm packages, database or server-side application.

## Deploy on Netlify

1. In Netlify, choose **Add new project → Import an existing project**.
2. Connect this GitHub repository.
3. Keep the repository root as the base directory. Netlify reads `netlify.toml`:
   - Build command: `python3 scripts/build_site.py`
   - Publish directory: `.site-build`
4. Deploy. Later pushes to the connected production branch deploy automatically.

Alternatively, run the build above and upload the **contents of `.site-build`** using Netlify’s manual deploy interface.

`.netlify/` is in `.gitignore`: local account/site-link files must stay out of Git. No credentials or environment variables are required by the website.

## Images and demonstrations

The on-device gallery shows four original Canon EOS M screenshots captured by MAXmade: the controls menu and three LiveView scenes. The images in `site/assets/screenshots/` are lossless WebP conversions of the original BMPs, at 720 × 480 with camera overlays intact. The README uses these same files. These are screen captures, not exported CR2 photos.

The playground's sample scene is AI-generated and clearly labelled as an illustration. The browser calculates the reflections; these are not claimed to be camera sample photos. The camera module itself uses no AI. Visitors can try a JPG, PNG or WebP locally in their browser; the file is not uploaded.

See [visual credits](../site/assets/CREDITS.md). Fonts are self-hosted under their included SIL Open Font Licenses.

The site’s download links serve the same immutable 0.2.0 ZIP and module as the GitHub release. Run `python scripts/verify_release.py` before changing release files.
