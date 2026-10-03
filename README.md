# AI-Driven Study Intelligence Platform

An AI-powered study platform that transforms educational materials into structured notes, document-grounded answers, topic-based quizzes, learner analytics, and personalized study recommendations.

## ✨ Features

- 📄 **Hybrid Document Processing** – Supports text PDFs, scanned documents, handwritten notes, and image-rich material using PDF extraction and OCR.
- 🧠 **Document Understanding** – Identifies topics, sections, concepts, and document structure.
- 📝 **AI Note Generation** – Generates structured, source-grounded notes in:
  - Full-Material Mode
  - Topic-Focused Mode
- 🔍 **Semantic Retrieval** – Uses semantic chunking and embeddings for relevant content retrieval.
- 💬 **Learn & Ask** – RAG-based question answering grounded in uploaded study material.
- 📝 **AI Quizzes** – Topic-based assessment with attempt and performance tracking.
- 📊 **Learning Analytics** – Tracks scores, study activity, weak topics, and progress.
- 📈 **Dashboard** – Displays learner performance, activity, streaks, and revision priorities.
- 🔄 **Adaptive Recommendations** – Recommends revision, practice, or reassessment based on learner activity.

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
