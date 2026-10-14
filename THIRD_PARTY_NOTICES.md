# Third Party Notices

OpenVMA source code is licensed under [MIT](LICENSE). Dependencies, downloaded model weights, container software and user-supplied media retain their own licenses; the project license does not replace those terms.

## Repository visuals

| Asset | Source | License / usage |
| --- | --- | --- |
| `frontend/public/branding/*.svg`, `frontend/public/favicon.svg` | OpenVMA repository branding | MIT; attribution retained through the project copyright notice |
| `frontend/public/media/showcase/orbit-concept.svg` | Original vector concept illustration created for OpenVMA | MIT; static illustration, not a generated video |
| `frontend/public/media/showcase/moon-concept.svg` | Original vector concept illustration created for OpenVMA | MIT; static illustration, not a photograph |
| `frontend/public/media/showcase/night-sky-concept.svg` | Original vector concept illustration created for OpenVMA | MIT; static illustration, not a photograph |
| `frontend/pages/public/branding/*.svg` | Copies of OpenVMA repository branding for the isolated Pages build | MIT |
| `frontend/public/media/showcase/asteroid-mission-concept.jpg` | [NASA Photojournal PIA19349](https://science.nasa.gov/photojournal/nasas-asteroid-redirect-robotic-mission-artist-concept/); credit: NASA. Embedded XMP confirms the image ID. | [NASA media guidelines](https://www.nasa.gov/nasa-brand-center/images-and-media/); acknowledge NASA and do not imply endorsement; not MIT |
| `frontend/public/media/showcase/moonset-from-orbit.jpg` | [The Moon as seen from the Space Station](https://www.esa.int/ESA_Multimedia/Images/2019/03/The_Moon_as_seen_from_the_Space_Station); credit: © ESA/NASA, Tim Peake | [ESA Standard Licence](https://www.esa.int/ESA_Multimedia/Terms_and_conditions_of_use_of_images_and_videos_available_on_the_esa_website); informational/editorial/educational use with credit; commercial use requires separate written authorization; not MIT |
| `frontend/public/media/showcase/cinematic/milky-way-kandersteg.webp` | [Milky Way Galaxy and Kandersteg viewed from the Blümlisalphütte at night](https://commons.wikimedia.org/wiki/File:Milky_Way_Galaxy_and_Kandersteg_viewed_from_the_Bl%C3%BCmlisalph%C3%BCtte_at_night.jpg); credit: Deralpinbergsteiger | [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/); local reference was resized and converted from JPEG to WebP; not MIT |
| `frontend/pages/public/media/showcase/` | Copies of the three original homepage references for the isolated Pages build | Same source terms as the corresponding references above |
| `docs/assets/workspace-smoke.jpg` | Screenshot of the real local application using an original FFmpeg test pattern and synthetic test data | MIT; no external media or AI output |

On 2026-10-14 the original homepage images were restored byte-for-byte for the local showcase, replacing the SVG stand-ins. These are visual references, not OpenVMA-generated media. NASA's image ID is confirmed in the local file; the Moon and Alpine source associations follow the original filenames and image descriptions, and a direct external visual comparison remains outstanding after a browser timeout. Before public publication, confirm those associations and the ESA image's applicability to the intended promotional use. No separate ESA commercial authorization has been verified. Restoration does not relicense these references under MIT. The original SVG stand-ins remain available in the application's public directory.

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

DashScope and Agnes are external services. Their model availability, data processing, output rights, pricing and service terms apply independently of OpenVMA's MIT license. Do not present this project as granting commercial rights to third-party model outputs or uploaded media.
