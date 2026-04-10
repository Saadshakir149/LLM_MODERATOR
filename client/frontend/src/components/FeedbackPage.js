// =========================
// FeedbackPage.js - MINIMALIST PROFESSIONAL DESIGN
// =========================
import React, { useEffect, useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkBreaks from "remark-breaks";
import rehypeSanitize from "rehype-sanitize";
import { MdArrowBack, MdDownload, MdShare, MdStar } from "react-icons/md";

const FEEDBACK_MARKDOWN_COMPONENTS = {
  p: ({ children, ...rest }) => (
    <p className="mb-3 last:mb-0 text-gray-700 leading-relaxed" {...rest}>
      {children}
    </p>
  ),
  strong: ({ children, ...rest }) => (
    <strong className="font-semibold text-gray-900" {...rest}>
      {children}
    </strong>
  ),
  em: ({ children, ...rest }) => (
    <em className="italic text-gray-700" {...rest}>
      {children}
    </em>
  ),
  ul: ({ children, ...rest }) => (
    <ul className="list-disc pl-5 space-y-1 mb-3 text-gray-700" {...rest}>
      {children}
    </ul>
  ),
  ol: ({ children, ...rest }) => (
    <ol className="list-decimal pl-5 space-y-1 mb-3 text-gray-700" {...rest}>
      {children}
    </ol>
  ),
  li: ({ children, ...rest }) => (
    <li className="leading-relaxed" {...rest}>
      {children}
    </li>
  ),
  h1: ({ children, ...rest }) => (
    <h1 className="text-xl font-bold text-gray-900 mt-2 mb-3" {...rest}>
      {children}
    </h1>
  ),
  h2: ({ children, ...rest }) => (
    <h2 className="text-lg font-semibold text-gray-900 mt-4 mb-2" {...rest}>
      {children}
    </h2>
  ),
  h3: ({ children, ...rest }) => (
    <h3 className="text-base font-semibold text-indigo-800 mt-3 mb-2" {...rest}>
      {children}
    </h3>
  ),
};

function deriveNameFromGreeting(text) {
  if (!text || typeof text !== "string") return "";
  const m = text.match(/Hi\s+([^,]+),/i);
  return m ? m[1].trim() : "";
}

export default function FeedbackPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const [feedback, setFeedback] = useState("");
  const [loading, setLoading] = useState(true);
  const [studentName, setStudentName] = useState("");

  useEffect(() => {
    const stateFeedback = location.state?.feedback;
    const fromNavName = (location.state?.studentName || "").trim();
    const targetUser = (location.state?.targetUsername || "").trim();

    if (stateFeedback) {
      setFeedback(stateFeedback);
      setStudentName(
        fromNavName || targetUser || deriveNameFromGreeting(stateFeedback)
      );
      setLoading(false);
      return;
    }

    const savedFeedback = localStorage.getItem("lastFeedback");
    if (savedFeedback) {
      setFeedback(savedFeedback);
      setStudentName(deriveNameFromGreeting(savedFeedback));
    }
    setLoading(false);
  }, [location.state]);

  const downloadFeedback = () => {
    const element = document.createElement("a");
    const file = new Blob([feedback], { type: "text/plain" });
    element.href = URL.createObjectURL(file);
    element.download = `feedback-${studentName || "session"}-${new Date().toISOString().split("T")[0]}.txt`;
    document.body.appendChild(element);
    element.click();
    document.body.removeChild(element);
  };

  const shareFeedback = () => {
    if (navigator.share) {
      navigator
        .share({
          title: `Feedback for ${studentName || "Session"}`,
          text: feedback,
        })
        .catch(() => copyToClipboard());
    } else {
      copyToClipboard();
    }
  };

  const copyToClipboard = () => {
    navigator.clipboard.writeText(feedback);
    alert("✅ Feedback copied to clipboard");
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <div className="w-12 h-12 border-4 border-gray-200 border-t-indigo-600 rounded-full animate-spin mx-auto mb-4"></div>
          <p className="text-gray-600">Loading feedback...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 py-12 px-4 sm:px-6 lg:px-8">
      <div className="max-w-3xl mx-auto">
        <button
          onClick={() => navigate("/")}
          className="flex items-center gap-2 text-gray-600 hover:text-indigo-600 mb-8 transition-colors group"
        >
          <MdArrowBack className="group-hover:-translate-x-1 transition-transform" />
          <span>Back to Dashboard</span>
        </button>

        <div className="bg-white rounded-2xl shadow-sm border border-gray-200 overflow-hidden">
          <div className="px-8 py-6 border-b border-gray-200">
            <div className="flex items-center justify-between">
              <div>
                <h1 className="text-2xl font-semibold text-gray-900">Session Feedback</h1>
                <p className="text-sm text-gray-500 mt-1">
                  {studentName ? `For ${studentName}` : "Personalized assessment"}
                </p>
              </div>
              <div className="flex items-center gap-1">
                {[1, 2, 3, 4, 5].map((star) => (
                  <MdStar key={star} className="w-5 h-5 text-yellow-400" />
                ))}
              </div>
            </div>
          </div>

          <div className="px-8 py-6 feedback-content max-w-none">
            {feedback ? (
              <ReactMarkdown
                remarkPlugins={[remarkGfm, remarkBreaks]}
                rehypePlugins={[rehypeSanitize]}
                components={FEEDBACK_MARKDOWN_COMPONENTS}
              >
                {feedback}
              </ReactMarkdown>
            ) : (
              <p className="text-gray-600">No feedback text is available for this session.</p>
            )}
          </div>

          <div className="px-8 py-4 bg-gray-50 border-t border-gray-200 flex justify-end gap-3">
            <button
              onClick={downloadFeedback}
              disabled={!feedback}
              className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors flex items-center gap-2 disabled:opacity-50"
            >
              <MdDownload className="w-4 h-4" />
              Download
            </button>
            <button
              onClick={shareFeedback}
              disabled={!feedback}
              className="px-4 py-2 text-sm font-medium text-white bg-indigo-600 rounded-lg hover:bg-indigo-700 transition-colors flex items-center gap-2 disabled:opacity-50"
            >
              <MdShare className="w-4 h-4" />
              Share
            </button>
          </div>
        </div>

        <div className="mt-6 bg-white rounded-xl border border-gray-200 p-4">
          <div className="flex items-center justify-between text-sm">
            <span className="text-gray-600">Session completed</span>
            <span className="text-gray-900 font-medium">
              {new Date().toLocaleDateString("en-US", {
                month: "short",
                day: "numeric",
                year: "numeric",
              })}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
