import hashlib
import json
import os
import re
import time
from pathlib import Path

import pymupdf
from dotenv import load_dotenv
from google import genai
from google.genai import types
from google.cloud import vision


load_dotenv()


# ============================================================
# CONFIGURATION
# ============================================================

# ------------------------------------------------------------
# Vision provider
#
# Current:
#   gemini
#
# Later we can add:
#   grok
#   openai
#   local
#
# The rest of this file does NOT depend on the provider.
# ------------------------------------------------------------

VISION_PROVIDER = os.getenv(
    "VISION_PROVIDER",
    "google",
).lower().strip()


# ------------------------------------------------------------
# Google Cloud Vision configuration
# ------------------------------------------------------------

# Hard safety limit per uploaded document.
MAX_VISION_PAGES_PER_DOCUMENT = int(
    os.getenv(
        "MAX_VISION_PAGES_PER_DOCUMENT",
        "100",
    )
)

# Conservative application-side monthly limit.
# Google Vision currently provides a monthly free tier; keep
# this below that limit as a safety margin.
MAX_VISION_PAGES_PER_MONTH = int(
    os.getenv(
        "MAX_VISION_PAGES_PER_MONTH",
        "900",
    )
)

# Google batchAnnotateImages supports multiple images per request.
# Keep this <= 16.
VISION_BATCH_SIZE = min(
    int(
        os.getenv(
            "VISION_BATCH_SIZE",
            "8",
        )
    ),
    16,
)

# Local usage counter. This stores ONLY a page count, not OCR text.
VISION_USAGE_FILE = Path(
    os.getenv(
        "VISION_USAGE_FILE",
        ".vision_usage.json",
    )
)


# ------------------------------------------------------------
# Gemini configuration
# ------------------------------------------------------------

GEMINI_API_KEY = os.getenv(
    "GEMINI_API_KEY"
)

GEMINI_MODEL = os.getenv(
    "GEMINI_MODEL",
    "gemini-3.6-flash",
)


# ------------------------------------------------------------
# Maximum output tokens
# ------------------------------------------------------------

VISION_MAX_OUTPUT_TOKENS = int(
    os.getenv(
        "VISION_MAX_OUTPUT_TOKENS",
        "8192",
    )
)


# ------------------------------------------------------------
# Retry configuration
# ------------------------------------------------------------

VISION_MAX_RETRIES = int(
    os.getenv(
        "VISION_MAX_RETRIES",
        "2",
    )
)


# ------------------------------------------------------------
# Persistent extraction cache
# ------------------------------------------------------------

VISION_CACHE_FILE = Path(
    os.getenv(
        "VISION_CACHE_FILE",
        ".vision_extraction_cache.json",
    )
)


# ============================================================
# GEMINI CLIENT
# ============================================================

gemini_client = None


if VISION_PROVIDER == "gemini":

    if not GEMINI_API_KEY:

        print(
            "WARNING: GEMINI_API_KEY is not set."
        )

    else:

        gemini_client = genai.Client(
            api_key=GEMINI_API_KEY
        )


# ============================================================
# GOOGLE CLOUD VISION CLIENT
# ============================================================

vision_client = None


if VISION_PROVIDER == "google":

    try:

        vision_client = vision.ImageAnnotatorClient()

        print(
            "Google Cloud Vision client initialized."
        )

    except Exception as e:

        print(
            "WARNING: Google Cloud Vision client could not "
            f"be initialized: {e}"
        )


# ============================================================
# VISION EXTRACTION PROMPT
# ============================================================

VISION_EXTRACTION_PROMPT = """
You are a high-accuracy educational document extraction system.

You are receiving one or more PDF page images.

Your job is to TRANSCRIBE the visible educational content.

Do NOT summarize it.

For every page, return the extracted content under the
EXACT page marker supplied below.

Required format:

[[PAGE_101]]
content from page 101

[[PAGE_102]]
content from page 102

[[PAGE_103]]
content from page 103

Rules:

1. Process EVERY supplied page.

2. NEVER merge two pages into one page.

3. NEVER change the page numbers.

4. Preserve the logical reading order of each page.

5. Extract headings and subheadings.

6. Extract paragraphs.

7. Extract bullet points and numbered lists.

8. Extract tables and preserve their structure using Markdown.

9. Extract mathematical formulas as accurately as possible.

10. Extract labels and text inside diagrams, charts, figures,
screenshots, and images when readable.

11. If a diagram contains important educational information,
describe the visible diagram accurately.

12. Preserve names, numbers, formulas, definitions, examples,
keywords, and labels.

13. Handwritten text must be transcribed as accurately as possible.

14. If handwriting or text is genuinely unreadable, write
[UNREADABLE] rather than guessing.

15. NEVER invent missing words or information.

16. NEVER summarize.

17. NEVER add explanations that are not present on the page.

18. NEVER add an introduction or conclusion.

19. Do not omit readable educational content.

20. Preserve mathematical notation and symbols whenever readable.

21. Keep every page completely separate using its supplied marker.

22. Do not add markdown fences around the response.

23. Do not add comments about the extraction process.

Return ONLY the page markers and extracted content.
"""


# ============================================================
# CACHE
# ============================================================

def _load_vision_cache():
    """
    Load persistent page-level Vision cache.
    """

    if not VISION_CACHE_FILE.exists():

        return {}

    try:

        with open(
            VISION_CACHE_FILE,
            "r",
            encoding="utf-8",
        ) as file:

            data = json.load(file)

        if isinstance(data, dict):

            return data

    except Exception as e:

        print(
            f"WARNING: Could not load Vision cache: {e}"
        )

    return {}


def _save_vision_cache(cache):
    """
    Save persistent Vision cache safely.
    """

    try:

        temporary_file = (
            VISION_CACHE_FILE.with_suffix(
                ".tmp"
            )
        )

        with open(
            temporary_file,
            "w",
            encoding="utf-8",
        ) as file:

            json.dump(
                cache,
                file,
                ensure_ascii=False,
                indent=2,
            )

        temporary_file.replace(
            VISION_CACHE_FILE
        )

    except Exception as e:

        print(
            f"WARNING: Could not save Vision cache: {e}"
        )


VISION_CACHE = _load_vision_cache()


# ============================================================
# GOOGLE VISION USAGE LIMIT
# ============================================================

def _load_vision_usage():
    """Load the current month's Vision page usage counter."""

    from datetime import datetime

    current_month = datetime.now().strftime("%Y-%m")

    if not VISION_USAGE_FILE.exists():

        return {
            "month": current_month,
            "pages": 0,
        }

    try:

        with open(
            VISION_USAGE_FILE,
            "r",
            encoding="utf-8",
        ) as file:

            data = json.load(file)

        if data.get("month") != current_month:

            return {
                "month": current_month,
                "pages": 0,
            }

        return {
            "month": current_month,
            "pages": int(data.get("pages", 0)),
        }

    except Exception as e:

        print(
            f"WARNING: Could not load Vision usage: {e}"
        )

        return {
            "month": current_month,
            "pages": 0,
        }


def _save_vision_usage(usage):
    """Persist only the Vision page counter; no OCR text is stored."""

    try:

        with open(
            VISION_USAGE_FILE,
            "w",
            encoding="utf-8",
        ) as file:

            json.dump(
                usage,
                file,
                indent=2,
            )

    except Exception as e:

        print(
            f"WARNING: Could not save Vision usage: {e}"
        )


def _get_vision_usage_count():
    """Return Vision pages used in the current calendar month."""

    return int(
        _load_vision_usage().get(
            "pages",
            0,
        )
    )


def _reserve_vision_pages(count):
    """Reserve Vision page units before making an API request."""

    if count <= 0:

        return True

    usage = _load_vision_usage()

    current = int(
        usage.get(
            "pages",
            0,
        )
    )

    if current + count > MAX_VISION_PAGES_PER_MONTH:

        print(
            "VISION MONTHLY LIMIT REACHED: "
            f"{current}/{MAX_VISION_PAGES_PER_MONTH} pages used. "
            f"Requested {count} more."
        )

        return False

    usage["pages"] = current + count

    _save_vision_usage(usage)

    return True


# ============================================================
# PAGE HASH
# ============================================================

def _page_hash(page):
    """
    Create a stable hash from the rendered page image.

    Same page image = same hash.

    This allows already extracted pages to be reused.
    """

    image_bytes = page_to_png(
        page
    )

    return hashlib.sha256(
        image_bytes
    ).hexdigest()


# ============================================================
# PAGE ANALYSIS
# ============================================================

def analyze_page(page):
    """
    Analyze one PDF page locally.

    No API call is made.
    """

    text = page.get_text(
        "text"
    ).strip()

    characters = len(text)

    words = len(
        text.split()
    )

    page_width = page.rect.width

    page_height = page.rect.height

    page_area = (
        page_width
        * page_height
    )

    images = page.get_images(
        full=True
    )

    image_area = 0

    for img in images:

        xref = img[0]

        try:

            rects = page.get_image_rects(
                xref
            )

            for rect in rects:

                image_area += (
                    rect.width
                    * rect.height
                )

        except Exception:

            pass

    if page_area > 0:

        image_ratio = (
            image_area
            / page_area
        )

    else:

        image_ratio = 0

    return {
        "text": text,
        "characters": characters,
        "words": words,
        "images": len(images),
        "image_ratio": image_ratio,
        "page_width": page_width,
        "page_height": page_height,
    }


# ============================================================
# NATIVE vs VISION
# ============================================================

def choose_extraction_method(info):
    """
    Decide whether a PDF page should use native extraction
    or Vision OCR.

    WHY THIS FUNCTION EXISTS:
    -------------------------
    We do NOT want to send every PDF page to Google Vision.

    Normal selectable-text PDFs:
        -> use PyMuPDF
        -> no OCR/API call

    Handwritten / scanned / image-heavy pages:
        -> use Vision OCR

    This keeps extraction fast and avoids unnecessary Vision
    API usage while still supporting handwritten material.
    """

    characters = info.get("characters", 0)
    words = info.get("words", 0)
    images = info.get("images", 0)
    image_ratio = info.get("image_ratio", 0.0)

    # Image-dominant page: scanned, photographed, or handwritten.
    if image_ratio >= 0.75:
        return "vision"

    # Image exists but PyMuPDF extracted almost no text.
    if images > 0 and characters < 100:
        return "vision"

    # Image exists and native extraction is extremely weak.
    if images > 0 and words < 15:
        return "vision"

    # Otherwise, trust the PDF's selectable/native text.
    return "native"


# ============================================================
# PAGE → PNG
# ============================================================

def page_to_png(page):
    """
    Render a PDF page into a high-resolution PNG.

    WHY THIS FUNCTION EXISTS:
    -------------------------
    Vision receives the rendered page image.

    Handwritten notes often contain small handwriting,
    mathematical symbols, subscripts, superscripts,
    diagram labels, arrows, and coordinate values.

    Rendering at 2x gives Vision a clearer image than
    the original 1x rendering.

    No image file is permanently created.
    The PNG remains in memory as bytes.
    """

    scale = 2.0

    matrix = pymupdf.Matrix(
        scale,
        scale,
    )

    pix = page.get_pixmap(
        matrix=matrix,
        alpha=False,
    )

    return pix.tobytes("png")


# ============================================================
# ERROR DETECTION
# ============================================================

def _is_quota_error(error):
    """
    Detect quota/rate-limit errors.

    These must NOT be retried.
    """

    message = str(
        error
    ).upper()

    return (
        "429" in message
        or "RESOURCE_EXHAUSTED" in message
        or "QUOTA" in message
        or "RATE LIMIT" in message
    )


def _is_temporary_server_error(error):
    """
    Detect temporary server errors.
    """

    message = str(
        error
    ).upper()

    return (
        "503" in message
        or "UNAVAILABLE" in message
        or "500" in message
        or "INTERNAL" in message
    )


# ============================================================
# BATCH PROMPT
# ============================================================

def _build_batch_prompt(
    page_numbers
):
    """
    Add exact page markers to the prompt.
    """

    markers = "\n\n".join(
        f"[[PAGE_{page_number}]]"
        for page_number in page_numbers
    )

    return (
        VISION_EXTRACTION_PROMPT
        + "\n\n"
        + "The exact page markers you MUST use are:"
        + "\n\n"
        + markers
    )


# ============================================================
# RESPONSE PARSER
# ============================================================

def _parse_batch_response(
    response_text,
    page_numbers,
):
    """
    Parse multi-page Vision response.

    Returns:

        {
            1: "page 1 text",
            2: "page 2 text",
            ...
        }
    """

    if not response_text:

        return {
            page_number: ""
            for page_number in page_numbers
        }

    text = response_text.strip()

    matches = list(
        re.finditer(
            r"\[\[PAGE_(\d+)\]\]",
            text,
        )
    )

    if not matches:

        return {
            page_number: ""
            for page_number in page_numbers
        }

    results = {}

    for index, match in enumerate(
        matches
    ):

        page_number = int(
            match.group(1)
        )

        start = match.end()

        if (
            index + 1
            < len(matches)
        ):

            end = matches[
                index + 1
            ].start()

        else:

            end = len(text)

        content = text[
            start:end
        ].strip()

        results[
            page_number
        ] = content

    return {
        page_number: results.get(
            page_number,
            "",
        )
        for page_number in page_numbers
    }


# ============================================================
# PROVIDER INTERFACE
# ============================================================

def _extract_with_provider(
    pages,
    page_numbers,
):
    """
    Provider-independent Vision entry point.

    IMPORTANT:

    The PDF pipeline calls ONLY this function.

    Therefore we can change the AI provider later without
    changing the PDF extraction pipeline.
    """

    if VISION_PROVIDER == "gemini":

        return _extract_with_gemini(
            pages,
            page_numbers,
        )

    if VISION_PROVIDER == "google":

        return _extract_with_google_vision(
            pages,
            page_numbers,
        )

    if VISION_PROVIDER == "grok":

        return _extract_with_grok(
            pages,
            page_numbers,
        )

    if VISION_PROVIDER == "openai":

        return _extract_with_openai(
            pages,
            page_numbers,
        )

    raise RuntimeError(
        f"Unsupported VISION_PROVIDER: "
        f"{VISION_PROVIDER}"
    )


# ============================================================
# GOOGLE CLOUD VISION PROVIDER
# ============================================================

def _extract_with_google_vision(
    pages,
    page_numbers,
):
    """
    Google Cloud Vision OCR implementation.

    Each PDF page is rendered locally to PNG bytes and sent
    directly to Vision. No Cloud Storage is used.

    batch_annotate_images is used so several page images can be
    sent in one HTTP/gRPC request. Each page still counts as one
    Vision OCR unit for the application safety limit.
    """

    if vision_client is None:

        raise RuntimeError(
            "Google Cloud Vision client was not initialized. "
            "Check GOOGLE_APPLICATION_CREDENTIALS and billing."
        )

    if len(pages) != len(page_numbers):

        raise ValueError(
            "Number of pages does not match number of page numbers."
        )

    if not pages:

        return {}

    if not _reserve_vision_pages(len(pages)):

        raise RuntimeError(
            "Google Cloud Vision monthly application limit reached."
        )

    requests = []

    for page_number, page in zip(
        page_numbers,
        pages,
    ):

        print(
            f"    Preparing page {page_number} for Google Vision..."
        )

        image_bytes = page_to_png(page)

        requests.append(
            vision.AnnotateImageRequest(
                image=vision.Image(
                    content=image_bytes,
                ),
                features=[
                    vision.Feature(
                        type_=vision.Feature.Type.DOCUMENT_TEXT_DETECTION,
                    )
                ],
            )
        )

    try:

        print(
            f"  [GOOGLE] Sending {len(requests)} page(s) "
            "to Cloud Vision..."
        )

        response = vision_client.batch_annotate_images(
            requests=requests,
        )

        results = {}

        for page_number, page_response in zip(
            page_numbers,
            response.responses,
        ):

            if page_response.error.message:

                print(
                    f"  Google Vision error on page {page_number}: "
                    f"{page_response.error.message}"
                )
                results[page_number] = ""
                continue

            text = ""

            if page_response.full_text_annotation:

                text = (
                    page_response.full_text_annotation.text
                    or ""
                ).strip()

            results[page_number] = text

        return results

    except Exception:

        # The reservation was made before the API call. If the RPC
        # itself fails, refund the local counter because no reliable
        # per-page result was returned to us.
        usage = _load_vision_usage()
        usage["pages"] = max(
            0,
            int(usage.get("pages", 0)) - len(pages),
        )
        _save_vision_usage(usage)
        raise


# ============================================================
# GEMINI PROVIDER
# ============================================================

def _extract_with_gemini(
    pages,
    page_numbers,
):
    """
    Gemini Vision implementation.

    Sends the entire batch in ONE API request.
    """

    if not GEMINI_API_KEY:

        raise ValueError(
            "GEMINI_API_KEY is not set."
        )

    if gemini_client is None:

        raise RuntimeError(
            "Gemini client was not initialized."
        )

    prompt = _build_batch_prompt(
        page_numbers
    )

    contents = [
        types.Part.from_text(
            text=prompt
        )
    ]

    for page_number, page in zip(
        page_numbers,
        pages,
    ):

        print(
            f"    Preparing page "
            f"{page_number}..."
        )

        image_bytes = page_to_png(
            page
        )

        contents.append(
            types.Part.from_text(
                text=(
                    f"THIS IMAGE IS PAGE "
                    f"{page_number}."
                )
            )
        )

        contents.append(
            types.Part.from_bytes(
                data=image_bytes,
                mime_type="image/png",
            )
        )

    for attempt in range(
        VISION_MAX_RETRIES + 1
    ):

        try:

            print(
                f"  [{VISION_PROVIDER.upper()}] "
                f"Sending ONE request for "
                f"{len(page_numbers)} pages..."
            )

            response = (
                gemini_client
                .models
                .generate_content(
                    model=GEMINI_MODEL,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        max_output_tokens=(
                            VISION_MAX_OUTPUT_TOKENS
                        ),
                        temperature=0.0,
                    ),
                )
            )

            if not response.text:

                raise RuntimeError(
                    "Gemini returned an empty response."
                )

            return _parse_batch_response(
                response.text,
                page_numbers,
            )

        except Exception as error:

            if _is_quota_error(
                error
            ):

                print(
                    "  GEMINI QUOTA EXHAUSTED."
                )

                raise

            if (
                _is_temporary_server_error(
                    error
                )
                and attempt
                < VISION_MAX_RETRIES
            ):

                wait_seconds = (
                    2 ** attempt
                )

                print(
                    f"  Temporary Gemini "
                    f"error. Retrying in "
                    f"{wait_seconds}s..."
                )

                time.sleep(
                    wait_seconds
                )

                continue

            raise


# ============================================================
# FUTURE GROK PROVIDER
# ============================================================

def _extract_with_grok(
    pages,
    page_numbers,
):
    """
    Grok Vision provider placeholder.

    We intentionally do NOT make up an API implementation here.

    When we connect your actual Grok API, only this function
    needs to be implemented.
    """

    raise RuntimeError(
        "Grok Vision provider is not configured yet. "
        "Set VISION_PROVIDER=gemini for now."
    )


# ============================================================
# FUTURE OPENAI PROVIDER
# ============================================================

def _extract_with_openai(
    pages,
    page_numbers,
):
    """
    OpenAI Vision provider placeholder.

    Kept separate so the extraction pipeline does not need
    to change when another provider is added.
    """

    raise RuntimeError(
        "OpenAI Vision provider is not configured yet."
    )


# ============================================================
# PROCESS ONE VISION BATCH
# ============================================================

def _process_vision_batch(
    doc,
    page_numbers,
):
    """
    Process one batch.

    Cached pages are removed first.

    Only uncached pages consume API calls.
    """

    results = {}

    uncached_pages = []

    uncached_numbers = []

    for page_number in page_numbers:

        page = doc[
            page_number - 1
        ]

        page_hash = _page_hash(
            page
        )

        cached = VISION_CACHE.get(
            page_hash
        )

        if cached:

            cached_content = (
                cached.get(
                    "content",
                    "",
                )
                or ""
            ).strip()

            if cached_content:

                print(
                    f"    Page {page_number}: "
                    f"CACHE HIT"
                )

                results[
                    page_number
                ] = cached_content

                continue

        uncached_pages.append(
            page
        )

        uncached_numbers.append(
            page_number
        )

    # --------------------------------------------------------
    # Entire batch cached
    # --------------------------------------------------------

    if not uncached_pages:

        return results

    # --------------------------------------------------------
    # ONE provider request
    # --------------------------------------------------------

    batch_results = (
        _extract_with_provider(
            uncached_pages,
            uncached_numbers,
        )
    )

    # --------------------------------------------------------
    # Store results
    # --------------------------------------------------------

    for page_number in uncached_numbers:

        content = (
            batch_results.get(
                page_number,
                "",
            )
            or ""
        ).strip()

        results[
            page_number
        ] = content

        if content:

            page = doc[
                page_number - 1
            ]

            page_hash = _page_hash(
                page
            )

            VISION_CACHE[
                page_hash
            ] = {
                "content": content,
                "source": VISION_PROVIDER,
            }

    _save_vision_cache(
        VISION_CACHE
    )

    return results


# ============================================================
# MAIN PDF EXTRACTOR
# ============================================================

def extract_pdf_content(
    pdf_source
):
    """
    Complete hybrid PDF extraction pipeline.

    Supports:

        PDF path
        PDF bytes

    Pipeline:

        PDF
         ↓
        local analysis
         ↓
        ┌──────────────────────┐
        │                      │
        ▼                      ▼
      NATIVE                VISION
        │                      │
     0 API calls        batched provider
        │                      │
        └──────────┬───────────┘
                   ↓
             page-preserved
                results
    """

    # --------------------------------------------------------
    # Open PDF
    # --------------------------------------------------------

    if isinstance(
        pdf_source,
        (bytes, bytearray),
    ):

        doc = pymupdf.open(
            stream=bytes(
                pdf_source
            ),
            filetype="pdf",
        )

    else:

        doc = pymupdf.open(
            pdf_source
        )

    total_pages = len(
        doc
    )

    results = {}

    vision_page_numbers = []

    print(
        "\n========================================"
    )

    print(
        "PDF EXTRACTION STARTED"
    )

    print(
        "========================================\n"
    )

    print(
        f"Total pages: {total_pages}"
    )

    print(
        f"Vision provider: "
        f"{VISION_PROVIDER}"
    )

    print(
        f"Vision batch size: "
        f"{VISION_BATCH_SIZE}"
    )

    print(
        f"Max Vision pages/document: "
        f"{MAX_VISION_PAGES_PER_DOCUMENT}"
    )

    print(
        f"Vision pages used this month: "
        f"{_get_vision_usage_count()}/"
        f"{MAX_VISION_PAGES_PER_MONTH}"
    )

    print()

    # ========================================================
    # PHASE 1 — LOCAL ANALYSIS
    # ========================================================

    print(
        "PHASE 1: LOCAL PAGE ANALYSIS"
    )

    print(
        "----------------------------------------"
    )

    for page_number, page in enumerate(
        doc,
        start=1,
    ):

        info = analyze_page(
            page
        )

        method = (
            choose_extraction_method(
                info
            )
        )

        print(
            f"Page {page_number}/{total_pages} "
            f"-> {method.upper()} "
            f"({info['characters']} chars, "
            f"{info['words']} words, "
            f"image ratio "
            f"{info['image_ratio']:.2f})"
        )

        if method == "native":

            results[
                page_number
            ] = {
                "page": page_number,
                "source": "native",
                "content": (
                    info["text"] or ""
                ).strip(),
                "characters": len(
                    info["text"] or ""
                ),
                "status": "complete",
            }

        else:

            vision_page_numbers.append(
                page_number
            )

    print()

    print(
        f"Native pages: "
        f"{total_pages - len(vision_page_numbers)}"
    )

    print(
        f"Vision candidates: "
        f"{len(vision_page_numbers)}"
    )

    # --------------------------------------------------------
    # HARD PER-DOCUMENT OCR LIMIT
    # --------------------------------------------------------

    vision_limit_reached = False

    if len(vision_page_numbers) > MAX_VISION_PAGES_PER_DOCUMENT:

        print()
        print(
            "VISION DOCUMENT LIMIT REACHED"
        )
        print(
            f"Candidate pages: {len(vision_page_numbers)}"
        )
        print(
            f"Maximum allowed: {MAX_VISION_PAGES_PER_DOCUMENT}"
        )
        print(
            "Only the first "
            f"{MAX_VISION_PAGES_PER_DOCUMENT} Vision candidates "
            "will be processed. Remaining pages will be marked "
            "pending_vision."
        )

        allowed_vision_pages = vision_page_numbers[:MAX_VISION_PAGES_PER_DOCUMENT]
        blocked_vision_pages = vision_page_numbers[MAX_VISION_PAGES_PER_DOCUMENT:]
        vision_page_numbers = allowed_vision_pages
        vision_limit_reached = True

        for page_number in blocked_vision_pages:

            results[page_number] = {
                "page": page_number,
                "source": "vision",
                "content": "",
                "characters": 0,
                "status": "pending_vision",
            }

    # ========================================================
    # PHASE 2 — VISION
    # ========================================================

    if vision_page_numbers:

        print()

        print(
            "PHASE 2: VISION EXTRACTION"
        )

        print(
            "----------------------------------------"
        )

        batches = []

        for start in range(
            0,
            len(
                vision_page_numbers
            ),
            VISION_BATCH_SIZE,
        ):

            batches.append(
                vision_page_numbers[
                    start:
                    start
                    + VISION_BATCH_SIZE
                ]
            )

        quota_exhausted = False

        for batch_index, batch in enumerate(
            batches,
            start=1,
        ):

            # ------------------------------------------------
            # Do not pretend we are processing a batch after
            # quota exhaustion.
            # ------------------------------------------------

            if quota_exhausted:

                for page_number in batch:

                    results[
                        page_number
                    ] = {
                        "page": page_number,
                        "source": "vision",
                        "content": "",
                        "characters": 0,
                        "status": "pending_vision",
                    }

                continue

            print()

            print(
                f"Vision batch "
                f"{batch_index}/"
                f"{len(batches)}"
            )

            print(
                f"Pages: {batch}"
            )

            try:

                batch_results = (
                    _process_vision_batch(
                        doc,
                        batch,
                    )
                )

                for page_number in batch:

                    content = (
                        batch_results.get(
                            page_number,
                            "",
                        )
                        or ""
                    ).strip()

                    if content:

                        status = "complete"

                    else:

                        status = (
                            "pending_vision"
                        )

                    results[
                        page_number
                    ] = {
                        "page": page_number,
                        "source": "vision",
                        "content": content,
                        "characters": len(
                            content
                        ),
                        "status": status,
                    }

                    print(
                        f"  Page {page_number}: "
                        f"{len(content)} chars "
                        f"({status})"
                    )

            except Exception as error:

                if (
                    _is_quota_error(error)
                    or "monthly application limit" in str(error).lower()
                ):

                    quota_exhausted = True

                    print()

                    print(
                        "VISION REQUESTS STOPPED"
                    )

                    print(
                        "Provider quota or application Vision limit "
                        "has been reached."
                    )

                    print(
                        "All remaining Vision pages "
                        "will be marked pending."
                    )

                else:

                    print(
                        f"Vision batch failed: "
                        f"{error}"
                    )

                for page_number in batch:

                    results[
                        page_number
                    ] = {
                        "page": page_number,
                        "source": "vision",
                        "content": "",
                        "characters": 0,
                        "status": "pending_vision",
                    }

    # ========================================================
    # PHASE 3 — ORDER RESULTS
    # ========================================================

    ordered_results = []

    for page_number in range(
        1,
        total_pages + 1,
    ):

        result = results.get(
            page_number
        )

        if result is None:

            result = {
                "page": page_number,
                "source": "unknown",
                "content": "",
                "characters": 0,
                "status": "failed",
            }

        ordered_results.append(
            result
        )

    doc.close()

    # ========================================================
    # SUMMARY
    # ========================================================

    native_count = sum(
        1
        for result in ordered_results
        if result[
            "source"
        ] == "native"
    )

    vision_complete_count = sum(
        1
        for result in ordered_results
        if (
            result["source"]
            == "vision"
            and result["status"]
            == "complete"
        )
    )

    pending_count = sum(
        1
        for result in ordered_results
        if result[
            "status"
        ] == "pending_vision"
    )

    print()

    print(
        "========================================"
    )

    print(
        "PDF EXTRACTION COMPLETE"
    )

    print(
        "========================================"
    )

    print(
        f"Total pages       : "
        f"{total_pages}"
    )

    print(
        f"Native pages      : "
        f"{native_count}"
    )

    print(
        f"Vision completed  : "
        f"{vision_complete_count}"
    )

    print(
        f"Vision pending    : "
        f"{pending_count}"
    )

    print()

    return ordered_results


# ============================================================
# COMBINE ALL PAGES
# ============================================================

def combine_extracted_content(
    results
):
    """
    Combine page results while preserving
    [[PAGE_N]] markers.
    """

    sections = []

    for result in results:

        page_number = result[
            "page"
        ]

        content = (
            result.get(
                "content",
                "",
            )
            or ""
        ).strip()

        status = result.get(
            "status",
            "complete",
        )

        if content:

            page_text = content

        elif status == "pending_vision":

            page_text = (
                "[VISION_EXTRACTION_PENDING]"
            )

        else:

            page_text = ""

        sections.append(
            f"[[PAGE_{page_number}]]\n"
            f"{page_text}"
        )

    return "\n\n".join(
        sections
    )