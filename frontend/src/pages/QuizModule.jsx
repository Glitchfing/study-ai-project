import React, { useCallback, useEffect, useMemo, useState } from "react";
import { getQuiz, saveQuizAttempt } from "../services/api";

const TOPICS = ["all", "nlp", "ml", "ds"];

function isMcq(question) {
  return question?.options?.length > 0 && (question.type || "mcq") === "mcq";
}

export default function QuizModule({ toast, refreshDashboard, selectedNoteId }) {
  const [topic, setTopic] = useState("all");
  const [quizMeta, setQuizMeta] = useState(null);
  const [questions, setQuestions] = useState([]);
  const [current, setCurrent] = useState(0);
  const [selected, setSelected] = useState(null);
  const [answerText, setAnswerText] = useState("");
  const [selfAssessment, setSelfAssessment] = useState(null);
  const [revealed, setRevealed] = useState(false);
  const [score, setScore] = useState(0);
  const [responses, setResponses] = useState([]);
  const [finished, setFinished] = useState(false);
  const [timeLeft, setTimeLeft] = useState(60);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  const loadQuiz = useCallback((nextTopic = topic, noteId = selectedNoteId) => {
    setLoading(true);
    getQuiz(nextTopic, noteId ? 12 : 5, noteId)
      .then((data) => {
        setQuizMeta(data);
        setQuestions(data.questions || []);
        setCurrent(0);
        setSelected(null);
        setAnswerText("");
        setSelfAssessment(null);
        setRevealed(false);
        setScore(0);
        setResponses([]);
        setFinished(false);
        setTimeLeft(noteId ? 90 : 60);
      })
      .catch(() => toast("Could not load quiz", "coral"))
      .finally(() => setLoading(false));
  }, [topic, selectedNoteId, toast]);

  useEffect(() => {
    loadQuiz(topic, selectedNoteId);
  }, [selectedNoteId]);

  useEffect(() => {
    if (finished || revealed || questions.length === 0) return;
    if (timeLeft <= 0) {
      handleReveal();
      return;
    }
    const timer = setTimeout(() => setTimeLeft((value) => value - 1), 1000);
    return () => clearTimeout(timer);
  }, [timeLeft, finished, revealed, questions.length]);

  const q = questions[current];
  const currentIsMcq = isMcq(q);
  const completedPct = questions.length ? Math.round((current / questions.length) * 100) : 0;
  const resultPct = questions.length ? Math.round((score / questions.length) * 100) : 0;
  const title = selectedNoteId ? quizMeta?.note_title || "Generated Note Quiz" : quizMeta?.topic_label || "Practice Quiz";

  const canSubmit = useMemo(() => {
    if (!q) return false;
    if (currentIsMcq) return selected !== null;
    return answerText.trim().length >= 12 || timeLeft <= 0;
  }, [q, currentIsMcq, selected, answerText, timeLeft]);

  function handleSelect(index) {
    if (revealed) return;
    setSelected(index);
  }

  function handleReveal() {
    if (!canSubmit && timeLeft > 0) return;
    setRevealed(true);
    if (currentIsMcq) {
      toast(selected === q.correct ? "Correct answer" : "Review this one", selected === q.correct ? "teal" : "coral");
    }
  }

  function buildResponse(isCorrect) {
    return {
      question_id: q.id,
      question: q.question,
      type: q.type || "conceptual",
      topic: q.section_title || q.topic || title,
      selected_index: currentIsMcq ? selected : null,
      selected_answer: currentIsMcq ? q.options?.[selected] || "" : answerText.trim(),
      correct_index: q.correct,
      expected_answer: q.options?.[q.correct] || q.answer_hint || q.explanation || "",
      is_correct: isCorrect,
      difficulty: q.difficulty || "medium",
    };
  }

  async function finishAttempt(nextResponses, nextScore) {
    setSaving(true);
    const total = questions.length;
    const weakTopics = nextResponses
      .filter((response) => !response.is_correct)
      .map((response) => response.topic)
      .filter(Boolean);

    try {
      await saveQuizAttempt({
        note_id: quizMeta?.note_id || null,
        note_title: quizMeta?.note_title || null,
        topic: quizMeta?.topic || topic,
        topic_label: title,
        total,
        correct: nextScore,
        score: Math.round((nextScore / Math.max(total, 1)) * 100),
        responses: nextResponses,
        weak_topics: Array.from(new Set(weakTopics)),
      });
      if (typeof refreshDashboard === "function") {
        refreshDashboard();
      }
    } catch {
      toast("Could not save quiz attempt", "coral");
    } finally {
      setSaving(false);
      setFinished(true);
    }
  }

  function handleNext() {
    const isCorrect = currentIsMcq ? selected === q.correct : selfAssessment === true;
    const nextResponses = [...responses, buildResponse(isCorrect)];
    const nextScore = score + (isCorrect ? 1 : 0);
    setResponses(nextResponses);
    setScore(nextScore);

    if (current + 1 >= questions.length) {
      finishAttempt(nextResponses, nextScore);
      return;
    }

    setCurrent((value) => value + 1);
    setSelected(null);
    setAnswerText("");
    setSelfAssessment(null);
    setRevealed(false);
    setTimeLeft(selectedNoteId ? 90 : 60);
  }

  function startTopicQuiz(nextTopic) {
    setTopic(nextTopic);
    loadQuiz(nextTopic, null);
  }

  return (
    <div className="view active" id="view-quiz">
      <div className="section-label">Practice Quiz</div>

      <div style={{ display: "flex", gap: 8, marginBottom: 16, flexWrap: "wrap" }}>
        {selectedNoteId ? (
          <button className="btn btn-sm btn-secondary" onClick={() => loadQuiz(topic, selectedNoteId)}>
            Reload Generated Quiz
          </button>
        ) : (
          TOPICS.map((item) => (
            <button
              key={item}
              className={`btn btn-sm ${topic === item ? "btn-primary" : "btn-secondary"}`}
              onClick={() => startTopicQuiz(item)}
            >
              {item.toUpperCase()}
            </button>
          ))
        )}
        {!selectedNoteId ? (
          <button className="btn btn-sm btn-secondary" onClick={() => loadQuiz(topic, null)}>
            Shuffle
          </button>
        ) : null}
      </div>

      {loading ? (
        <div style={{ color: "var(--muted)", padding: 20 }}>Loading quiz...</div>
      ) : finished ? (
        <div className="card" style={{ padding: 32, textAlign: "center" }}>
          <div style={{ fontFamily: "'Syne', sans-serif", fontWeight: 800, fontSize: 32, color: "var(--c-bright)" }}>
            {resultPct}%
          </div>
          <div style={{ color: "var(--text2)", marginTop: 6 }}>
            {score} / {questions.length} correct
          </div>
          <div style={{ color: "var(--muted)", fontSize: 12, marginTop: 8 }}>
            {saving ? "Saving attempt..." : "Attempt saved. Dashboard recommendations will reflect this result."}
          </div>
          <button className="btn btn-primary" style={{ marginTop: 20 }} onClick={() => loadQuiz(topic, selectedNoteId)}>
            Try Again
          </button>
        </div>
      ) : q ? (
        <div className="quiz-layout">
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8, fontSize: 12, color: "var(--muted)" }}>
            <span>{title}</span>
            <span>Question {current + 1} / {questions.length}</span>
          </div>
          <div className="progress-bar" style={{ marginBottom: 16 }}>
            <div
              className="progress-fill"
              style={{
                width: `${completedPct}%`,
                background: "linear-gradient(90deg,var(--c-bright),var(--c-aqua))",
              }}
            />
          </div>

          <div className="card" style={{ padding: "22px 24px", marginBottom: 14 }}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 14, alignItems: "center", gap: 10 }}>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                <span className={`tag tag-${q.difficulty === "easy" ? "green" : q.difficulty === "medium" ? "teal" : "coral"}`}>
                  {(q.difficulty || "medium").toUpperCase()}
                </span>
                <span className="tag tag-teal">{(q.type || "conceptual").toUpperCase()}</span>
              </div>
              <span style={{
                fontFamily: "'Syne', sans-serif",
                fontWeight: 800,
                fontSize: 18,
                color: timeLeft <= 10 ? "var(--c-coral)" : "var(--c-bright)",
              }}>
                {timeLeft}s
              </span>
            </div>

            <div style={{ fontSize: 15, fontWeight: 600, color: "var(--text)", marginBottom: 20, lineHeight: 1.5 }}>
              {q.question}
            </div>

            {currentIsMcq ? (
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {q.options.map((option, index) => {
                  let bg = "var(--glass)";
                  let border = "var(--border)";
                  let color = "var(--text2)";
                  if (revealed) {
                    if (index === q.correct) {
                      bg = "rgba(100,182,172,0.2)";
                      border = "var(--c-aqua)";
                      color = "#a0e9e0";
                    } else if (index === selected) {
                      bg = "rgba(226,149,120,0.15)";
                      border = "var(--c-coral)";
                      color = "var(--c-blush)";
                    }
                  } else if (selected === index) {
                    bg = "rgba(17,157,164,0.15)";
                    border = "var(--c-bright)";
                    color = "var(--c-sky)";
                  }
                  return (
                    <div
                      key={index}
                      onClick={() => handleSelect(index)}
                      style={{
                        padding: "11px 14px",
                        borderRadius: 8,
                        background: bg,
                        border: `1px solid ${border}`,
                        color,
                        cursor: revealed ? "default" : "pointer",
                        transition: "all 0.2s",
                        display: "flex",
                        alignItems: "center",
                        gap: 10,
                      }}
                    >
                      <span style={{ fontWeight: 700, color: "var(--muted)", width: 20 }}>
                        {String.fromCharCode(65 + index)}.
                      </span>
                      {option}
                    </div>
                  );
                })}
              </div>
            ) : (
              <textarea
                value={answerText}
                onChange={(event) => setAnswerText(event.target.value)}
                disabled={revealed}
                placeholder="Write your answer in exam style..."
                style={{
                  width: "100%",
                  minHeight: 130,
                  borderRadius: 8,
                  border: "1px solid var(--border)",
                  background: "rgba(255,255,255,0.04)",
                  color: "var(--text)",
                  padding: 12,
                  resize: "vertical",
                  lineHeight: 1.6,
                }}
              />
            )}

            {revealed ? (
              <div style={{
                marginTop: 14,
                padding: "12px 14px",
                borderRadius: 8,
                background: "rgba(17,157,164,0.1)",
                border: "1px solid var(--border2)",
                fontSize: 12,
                color: "var(--text2)",
                lineHeight: 1.6,
              }}>
                <strong>Review:</strong> {q.explanation || q.answer_hint || "Compare your answer with the related note section."}
                {!currentIsMcq ? (
                  <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
                    <button
                      className={`btn btn-sm ${selfAssessment === true ? "btn-primary" : "btn-secondary"}`}
                      onClick={() => setSelfAssessment(true)}
                    >
                      I got this
                    </button>
                    <button
                      className={`btn btn-sm ${selfAssessment === false ? "btn-coral" : "btn-secondary"}`}
                      onClick={() => setSelfAssessment(false)}
                    >
                      Needs review
                    </button>
                  </div>
                ) : null}
              </div>
            ) : null}
          </div>

          <div style={{ display: "flex", gap: 10 }}>
            {!revealed ? (
              <button className="btn btn-primary" disabled={!canSubmit} onClick={handleReveal}>
                Submit Answer
              </button>
            ) : (
              <button
                className="btn btn-primary"
                disabled={!currentIsMcq && selfAssessment === null}
                onClick={handleNext}
              >
                {current + 1 >= questions.length ? "Save Results" : "Next Question"}
              </button>
            )}
          </div>
        </div>
      ) : (
        <div style={{ color: "var(--muted)" }}>No questions available for this note yet.</div>
      )}
    </div>
  );
}
