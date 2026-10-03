# AI-Driven Study Intelligence Platform for Active Learning

An AI-powered study intelligence platform that transforms diverse educational materials into structured study resources, document-grounded answers, topic-based assessments, learner analytics, and personalized learning recommendations.

The system combines hybrid document processing, OCR, document understanding, semantic retrieval, LLM-based note generation, Retrieval-Augmented Generation (RAG), quizzes, analytics, and adaptive recommendations into a unified learning workflow.

---

## 📌 Overview

Students often rely on multiple forms of study material, including textbooks, lecture notes, scanned PDFs, handwritten notes, diagrams, and other digital resources. Converting these materials into an organized learning process requires significant manual effort.

This project addresses this problem by providing an integrated AI-driven study platform that can:

- Process machine-readable and scanned documents
- Handle handwritten and image-rich study material
- Understand document structure and topics
- Generate structured, source-grounded study notes
- Generate notes for an entire study collection or a specific topic
- Provide document-grounded question answering using RAG
- Generate topic-based quizzes
- Track learner performance and study activity
- Identify weak topics and revision priorities
- Provide personalized learning recommendations
- Continuously update recommendations based on learner activity

The overall system is designed around an adaptive learning loop in which learner activity influences subsequent learning recommendations.

---

## 🎯 Objectives

The main objectives of the platform are:

1. To process heterogeneous educational documents using appropriate extraction techniques.
2. To understand the structure and semantic organization of study material.
3. To generate structured and source-grounded learning resources.
4. To support both complete-material and topic-focused learning.
5. To provide document-grounded question answering through Retrieval-Augmented Generation.
6. To assess learners at the topic level.
7. To analyze learner performance and study activity.
8. To identify topics requiring revision or additional practice.
9. To provide personalized learning recommendations.
10. To establish an adaptive learning cycle for continuous improvement.

---

## ✨ Key Features

### 1. 📄 Hybrid Document Processing

The platform supports different types of educational documents:

- Machine-readable PDFs
- Scanned PDFs
- Handwritten notes
- Image-rich documents
- Multiple related study documents
- Documents containing diagrams and other visual content

The system uses native PDF extraction for machine-readable pages and OCR for scanned, handwritten, and image-based pages.

```text
                Uploaded Material
                       │
                       ▼
              Document Classification
                       │
            ┌──────────┴──────────┐
            │                     │
            ▼                     ▼
     Machine-readable       Scanned / Image /
          PDF                Handwritten
            │                     │
            ▼                     ▼
      Native Extraction          OCR
            │                     │
            └──────────┬──────────┘
                       ▼
                 Unified Content
## 🏗️ Architecture

```text
Documents
   ↓
Hybrid Extraction / OCR
   ↓
Document Understanding
   ↓
Semantic Sections & Chunks
   ↓
Embeddings → Qdrant
   ↓
┌───────────────────────┐
│ Notes | RAG | Quizzes │
└───────────┬───────────┘
            ↓
     Learner Analytics
            ↓
 Dashboard & Recommendations
            ↓
    Adaptive Learning Loop

🛠️ Tech Stack

Frontend: React, CSS
Backend: Python, FastAPI, Uvicorn, Pydantic
Document Processing: PyMuPDF, PyPDF2, pypdf
OCR: Google Cloud Vision
LLMs: Groq API, Google Gemini API
Embeddings: BAAI/bge-small-en-v1.5
Vector Database: Qdrant

Environment Variables
Create a .env file:

GROQ_API_KEY=your_groq_api_key
GEMINI_API_KEY=your_gemini_api_key
GOOGLE_APPLICATION_CREDENTIALS=path_to_credentials.json


