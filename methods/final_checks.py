# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import json
import os.path as osp
import traceback


def run_final_checks(
    base_dir: str,
    final_pdf_path: str,
    refined_pdf_path: str,
    model_name: str,
    verify_references: bool = True,
    final_review: bool = True,
):
    """Runs post-generation checks; never raises so a finished paper is not lost.

    Writes `reference_verification.json` and `final_review.json` into base_dir.
    """
    if verify_references:
        try:
            from utils.reference_verifier import verify_files

            # The refinement agent writes <name>.tex next to <name>.pdf.
            workdir = osp.dirname(refined_pdf_path)
            tex_path = osp.splitext(refined_pdf_path)[0] + ".tex"
            if not osp.exists(tex_path):
                tex_path = osp.join(workdir, "raw_draft_paper.tex")
            report = verify_files(
                tex_path,
                osp.join(workdir, "references.bib"),
                osp.join(base_dir, "reference_verification.json"),
            )
            print(
                f" >> [RefCheck] cited={report['n_cited']} "
                f"missing={report['missing_keys']} "
                f"unverified={report['unverified_keys']}"
            )
        except Exception:
            print(" >> [RefCheck] failed:\n", traceback.format_exc())

    if final_review:
        try:
            from autoraters.agent_review import perform_review_agentreview
            from utils.pdf_utils import load_paper

            review = perform_review_agentreview(
                text=load_paper(pdf_path=final_pdf_path), model_name=model_name
            )
            with open(osp.join(base_dir, "final_review.json"), "w", encoding="utf-8") as f:
                json.dump(review, f, indent=2)
            print(f" >> [FinalReview] Overall: {review.get('Overall')}/10")
        except Exception:
            print(" >> [FinalReview] failed:\n", traceback.format_exc())
