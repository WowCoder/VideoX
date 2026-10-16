# Third Party Notices

VideoX source code is licensed under [MIT](LICENSE). Dependencies, downloaded model weights, container software and user-supplied media retain their own licenses; the project license does not replace those terms.

## Repository visuals

| Asset | Source | License / usage |
| --- | --- | --- |
| `frontend/public/branding/*.svg`, `frontend/public/favicon.svg` | VideoX repository branding | MIT; attribution retained through the project copyright notice |
| `frontend/public/media/showcase/orbit-concept.svg` | Original vector concept illustration created for VideoX | MIT; static illustration, not a generated video |
| `frontend/public/media/showcase/moon-concept.svg` | Original vector concept illustration created for VideoX | MIT; static illustration, not a photograph |
| `frontend/public/media/showcase/night-sky-concept.svg` | Original vector concept illustration created for VideoX | MIT; static illustration, not a photograph |
| `frontend/pages/public/branding/*.svg` | Copies of VideoX repository branding for the isolated Pages build | MIT |
| `frontend/public/media/showcase/asteroid-mission-concept.jpg` | [NASA Photojournal PIA19349](https://science.nasa.gov/photojournal/nasas-asteroid-redirect-robotic-mission-artist-concept/); credit: NASA. Embedded XMP confirms the image ID. | [NASA media guidelines](https://www.nasa.gov/nasa-brand-center/images-and-media/); acknowledge NASA and do not imply endorsement; not MIT |
| `frontend/public/media/showcase/moonset-from-orbit.jpg` | [Crescent Moon Rising and Earth’s Atmosphere](https://www.nasa.gov/image-article/crescent-moon-rising-earths-atmosphere/), NASA image ISS038e037342; credit: NASA | [NASA media guidelines](https://www.nasa.gov/nasa-brand-center/images-and-media/); acknowledge NASA and do not imply endorsement; not MIT |
| `frontend/public/media/showcase/cinematic/milky-way-kandersteg.webp` | [Milky Way Galaxy and Kandersteg viewed from the Blümlisalphütte at night](https://commons.wikimedia.org/wiki/File:Milky_Way_Galaxy_and_Kandersteg_viewed_from_the_Bl%C3%BCmlisalph%C3%BCtte_at_night.jpg); credit: Deralpinbergsteiger | [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/); local reference was resized and converted from JPEG to WebP; not MIT |
| `frontend/pages/public/media/showcase/` | Copies of the three original homepage references for the isolated Pages build | Same source terms as the corresponding references above |
| `docs/assets/workspace-smoke.jpg` | Screenshot of the real local application using an original FFmpeg test pattern and synthetic test data | MIT; no external media or AI output |
| `docs/assets/videox-workspace.jpg`, `videox-assets.jpg`, `videox-export.jpg` | Screenshots of a real local VideoX project with manually authored script, an original title card, and uploaded clips made from the two NASA references above | Application UI and original title card: MIT. NASA imagery: the same NASA media guidelines above, not MIT; credits retained here. Clips use resizing, cropping and slow pan/zoom; no AI-generated imagery and no NASA endorsement |

On 2026-10-14 all three original homepage references were verified against their primary sources. The asteroid concept has identical decoded pixels to NASA PIA19349; its file metadata differs. The Moon photo is byte-for-byte identical to NASA's [ISS038e037342 large rendition](https://images-assets.nasa.gov/image/iss038e037342/iss038e037342~large.jpg), SHA-256 `1ad1aa3f936655115e0be6f00fb3d9bca577e4861ce83ab714706e1f816f7ca4`. Its earlier ESA/Tim Peake attribution was incorrect. The Alpine image matches the author's Commons publication after resizing and conversion to WebP; this transformation is disclosed in the homepage credits. Preserve its author, source and CC BY-SA 4.0 notice; further adaptations must comply with ShareAlike. These are visual references, not VideoX-generated media, and NASA does not endorse VideoX. Restoration does not relicense these references under MIT. The original SVG stand-ins remain available in the application's public directory.

Lucide icons are distributed with the frontend dependency and follow [Lucide's license](https://github.com/lucide-icons/lucide/blob/main/LICENSE).

## Dependencies and runtime software

The exact frontend dependency tree is recorded in `frontend/package-lock.json`; Python dependency pins are in `backend/requirements.txt` and `local-ai/*/requirements.txt`. Consult each package's license and preserve the notices required by any redistributed package or image.

Deployment uses PostgreSQL/pgvector, Redis, MinIO, FFmpeg and Nginx images. Review the selected versions and build options when distributing an appliance or container bundle. In particular, MinIO and FFmpeg have their own licensing requirements. This file is an inventory, not a complete legal compatibility audit.

## Model weights and providers

Local weights are downloaded at runtime rather than committed to this repository. Check the model/repository license for the exact version you use:

- [BAAI/bge-m3](https://huggingface.co/BAAI/bge-m3)
- [BAAI/bge-reranker-v2-m3](https://huggingface.co/BAAI/bge-reranker-v2-m3)
- [FunASR](https://github.com/modelscope/FunASR) and the selected ASR model
- [RapidOCR](https://github.com/RapidAI/RapidOCR) and the selected OCR weights

DashScope and Agnes are external services. Their model availability, data processing, output rights, pricing and service terms apply independently of VideoX's MIT license. Do not present this project as granting commercial rights to third-party model outputs or uploaded media.
