import React, { useCallback, useEffect, useMemo, useState } from "react";
import { getQuiz, saveQuizAttempt } from "../services/api";

const TOPICS = ["all", "nlp", "ml", "ds"];

function isChoiceQuestion(question) {
  return (question?.options || []).length > 0;
}

function normalizeAnswer(value) {
  return String(value || "")
    .toLowerCase()
    .replace(/&/g, " and ")
    .replace(/[^a-z0-9\s]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function initialism(value) {
  const words = normalizeAnswer(value).split(" ").filter(Boolean);
  return words.length > 1 ? words.map((word) => word[0]).join("") : "";
}

function similarity(a, b) {
  const left = normalizeAnswer(a);
  const right = normalizeAnswer(b);
  if (!left || !right) return 0;
  const rows = Array.from({ length: left.length + 1 }, (_, index) => [index]);
  for (let j = 1; j <= right.length; j++) rows[0][j] = j;
  for (let i = 1; i <= left.length; i++) {
    for (let j = 1; j <= right.length; j++) {
      rows[i][j] = Math.min(
        rows[i - 1][j] + 1,
        rows[i][j - 1] + 1,
        rows[i - 1][j - 1] + (left[i - 1] === right[j - 1] ? 0 : 1)
      );
    }
  }
  const distance = rows[left.length][right.length];
  return 1 - distance / Math.max(left.length, right.length, 1);
}

function evaluateTextAnswer(question, answer) {
  const expected = [
    question.correct_answer,
    question.answer_hint,
    ...(question.acceptable_answers || []),
  ].filter(Boolean);
  const normalized = normalizeAnswer(answer);
  const accepted = expected.flatMap((item) => {
    const init = initialism(item);
    return init ? [normalizeAnswer(item), init] : [normalizeAnswer(item)];
  });
  if (accepted.some((item) => normalized === item || similarity(normalized, item) >= 0.86)) {
    return true;
  }

  const keywords = (question.expected_keywords || []).map(normalizeAnswer).filter(Boolean);
  if (!keywords.length) return false;
  const hits = keywords.filter((keyword) => normalized.includes(keyword) || normalized.split(" ").includes(keyword)).length;
  const keywordScore = hits / Math.max(keywords.length, 1);
  const semanticScore = Math.max(0, ...accepted.map((item) => similarity(normalized, item)));
  return keywordScore >= 0.5 || (keywordScore >= 0.34 && semanticScore >= 0.62);
}

function getPerformance(correct, total) {
  const score20 = Math.round((correct / Math.max(total, 1)) * 20);
  const percentage = Math.round((correct / Math.max(total, 1)) * 100);
  if (score20 >= 18) return { score20, percentage, emoji: "🥳", feedback: "Very Good", motivational_text: "Excellent work. Keep revising with mixed questions to stay sharp." };
  if (score20 >= 15) return { score20, percentage, emoji: "😄", feedback: "Good", motivational_text: "Nice progress. Review the missed points once and try a shuffled quiz." };
  if (score20 >= 10) return { score20, percentage, emoji: "🥺", feedback: "Better Next Time", motivational_text: "You are close. Re-read weak topics and answer them in your own words." };
  if (score20 >= 5) return { score20, percentage, emoji: "😦", feedback: "You Can Do Much Better", motivational_text: "Slow down, revise the basics, and retry with short answers first." };
  return { score20, percentage, emoji: "😞", feedback: "Do Hard Work", motivational_text: "Start again from the summary notes, then practice the easiest questions." };
}

export default function QuizModule({ toast, refreshDashboard, selectedNoteId }) {
  const [topic, setTopic] = useState("all");
  const [quizMeta, setQuizMeta] = useState(null);
  const [questions, setQuestions] = useState([]);
  const [current, setCurrent] = useState(0);
  const [selected, setSelected] = useState(null);
  const [answerText, setAnswerText] = useState("");
  const [revealed, setRevealed] = useState(false);
  const [currentCorrect, setCurrentCorrect] = useState(null);
  const [score, setScore] = useState(0);
  const [responses, setResponses] = useState([]);
  const [finished, setFinished] = useState(false);
  const [savedPerformance, setSavedPerformance] = useState(null);
  const [timeLeft, setTimeLeft] = useState(60);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  const loadQuiz = useCallback((nextTopic = topic, noteId = selectedNoteId) => {
    setLoading(true);
    getQuiz(nextTopic, noteId ? 20 : 10, noteId)
      .then((data) => {
        setQuizMeta(data);
        setQuestions(data.questions || []);
        setCurrent(0);
        setSelected(null);
        setAnswerText("");
        setRevealed(false);
        setCurrentCorrect(null);
        setScore(0);
        setResponses([]);
        setFinished(false);
        setSavedPerformance(null);
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
  const currentIsChoice = isChoiceQuestion(q);
  const completedPct = questions.length ? Math.round((current / questions.length) * 100) : 0;
  const localPerformance = getPerformance(score, questions.length);
  const performance = savedPerformance || localPerformance;
  const missedTopics = Array.from(new Set(responses.filter((item) => !item.is_correct).map((item) => item.topic).filter(Boolean))).slice(0, 3);
  const title = selectedNoteId ? quizMeta?.note_title || "Generated Note Quiz" : quizMeta?.topic_label || "Practice Quiz";

  const canSubmit = useMemo(() => {
    if (!q) return false;
    if (currentIsChoice) return selected !== null || timeLeft <= 0;
    return answerText.trim().length > 0 || timeLeft <= 0;
  }, [q, currentIsChoice, selected, answerText, timeLeft]);

  function handleSelect(index) {
    if (revealed) return;
    setSelected(index);
  }

  function judgeCurrentQuestion() {
    if (!q) return false;
    if (currentIsChoice) return selected === q.correct;
    return evaluateTextAnswer(q, answerText);
  }

  function handleReveal() {
    if (!canSubmit && timeLeft > 0) return;
    const isCorrect = judgeCurrentQuestion();
    setCurrentCorrect(isCorrect);
    setRevealed(true);
    toast(isCorrect ? "✅ Correct answer" : "💡 Review this one", isCorrect ? "teal" : "coral");
  }

  function buildResponse(isCorrect) {
    return {
      question_id: q.id,
      question: q.question,
      type: q.type || "mcq",
      topic: q.section_title || q.topic || title,
      selected_index: currentIsChoice ? selected : null,
      selected_answer: currentIsChoice ? q.options?.[selected] || "" : answerText.trim(),
      correct_index: q.correct,
      expected_answer: q.correct_answer || q.options?.[q.correct] || q.answer_hint || "",
      is_correct: isCorrect,
      difficulty: q.difficulty || "medium",
      question_data: q,
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
      const saved = await saveQuizAttempt({
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
      if (saved.performance) setSavedPerformance(saved.performance);
      if (typeof refreshDashboard === "function") refreshDashboard();
    } catch {
      toast("Could not save quiz attempt", "coral");
    } finally {
      setSaving(false);
      setFinished(true);
    }
  }

  function handleNext() {
    const isCorrect = currentCorrect === true;
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
    setRevealed(false);
    setCurrentCorrect(null);
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
        <button className="btn btn-sm btn-secondary" onClick={() => loadQuiz(topic, selectedNoteId || null)}>
          Shuffle
        </button>
      </div>

      {loading ? (
        <div style={{ color: "var(--muted)", padding: 20 }}>Loading quiz...</div>
      ) : finished ? (
        <div className="result-card card">
          <div className="result-emoji">{performance.emoji}</div>
          <div className="result-score">{score} / {questions.length}</div>
          <div className="result-percent">{performance.percentage}%</div>
          <div className="progress-bar" style={{ width: "100%", maxWidth: 360, margin: "12px auto 0" }}>
            <div
              className="progress-fill"
              style={{
                width: `${performance.percentage}%`,
                background: "linear-gradient(90deg,var(--c-coral),var(--c-bright),var(--c-aqua))",
              }}
            />
          </div>
          <div className="result-feedback">{performance.feedback}</div>
          <p className="result-motivation">
            {performance.motivational_text || "Review weak topics, retry with shuffled questions, and aim one level higher next time."}
          </p>
          {missedTopics.length ? (
            <div className="result-suggestions">
              <strong>Improve next:</strong> {missedTopics.join(", ")}
            </div>
          ) : null}
          <div style={{ color: "var(--muted)", fontSize: 12, marginTop: 8 }}>
            {saving ? "Saving attempt..." : "Attempt saved. Dashboard analytics now include this result."}
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
            <div className="progress-fill" style={{ width: `${completedPct}%`, background: "linear-gradient(90deg,var(--c-bright),var(--c-aqua))" }} />
          </div>

          <div className="card" style={{ padding: "22px 24px", marginBottom: 14 }}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 14, alignItems: "center", gap: 10 }}>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                <span className={`tag tag-${q.difficulty === "easy" ? "green" : q.difficulty === "medium" ? "teal" : "coral"}`}>
                  {(q.difficulty || "medium").toUpperCase()}
                </span>
                <span className="tag tag-teal">{(q.type || "mcq").replace("_", " ").toUpperCase()}</span>
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

            {currentIsChoice ? (
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
                      <span style={{ fontWeight: 700, color: "var(--muted)", width: 20 }}>{String.fromCharCode(65 + index)}.</span>
                      {option}
                    </div>
                  );
                })}
              </div>
            ) : q.type === "sentence" || q.type === "scenario" ? (
              <textarea
                value={answerText}
                onChange={(event) => setAnswerText(event.target.value)}
                disabled={revealed}
                placeholder={q.type === "scenario" ? "Answer with a short phrase or one sentence..." : "Answer in one concise sentence..."}
                style={{
                  width: "100%",
                  minHeight: 82,
                  borderRadius: 8,
                  border: "1px solid var(--border)",
                  background: "rgba(255,255,255,0.04)",
                  color: "var(--text)",
                  padding: "12px 14px",
                  lineHeight: 1.5,
                  resize: "vertical",
                }}
              />
            ) : (
              <input
                value={answerText}
                onChange={(event) => setAnswerText(event.target.value)}
                disabled={revealed}
                placeholder={q.type === "one_word" ? "Type one word or abbreviation..." : "Type the missing term..."}
                style={{
                  width: "100%",
                  borderRadius: 8,
                  border: "1px solid var(--border)",
                  background: "rgba(255,255,255,0.04)",
                  color: "var(--text)",
                  padding: "12px 14px",
                  lineHeight: 1.4,
                }}
              />
            )}

            {revealed ? (
              <div className={`answer-review ${currentCorrect ? "ok" : "bad"}`}>
                <strong>{currentCorrect ? "✅ Correct:" : "💡 Expected:"}</strong>{" "}
                {q.correct_answer || q.options?.[q.correct] || q.answer_hint}
                <br />
                <span>{q.explanation || "Compare this answer with the related note section."}</span>
              </div>
            ) : null}
          </div>

          <div style={{ display: "flex", gap: 10 }}>
            {!revealed ? (
              <button className="btn btn-primary" disabled={!canSubmit} onClick={handleReveal}>
                Submit Answer
              </button>
            ) : (
              <button className="btn btn-primary" onClick={handleNext}>
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
