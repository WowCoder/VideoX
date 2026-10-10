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
| `docs/assets/workspace-smoke.jpg` | Screenshot of the real local application using an original FFmpeg test pattern and synthetic test data | MIT; no external media or AI output |

Earlier showcase photos with incomplete provenance have been removed from the publishable source tree. They are not part of the standalone project website. Use your own media or assets with explicit redistribution permission in examples and demonstrations.

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
