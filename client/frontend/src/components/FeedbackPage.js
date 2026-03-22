// =========================
// FeedbackPage.js - MINIMALIST PROFESSIONAL DESIGN
// =========================
import React, { useEffect, useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { MdArrowBack, MdDownload, MdShare, MdStar } from "react-icons/md";

export default function FeedbackPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const [feedback, setFeedback] = useState("");
  const [loading, setLoading] = useState(true);
  const [studentName, setStudentName] = useState("");

  useEffect(() => {
    // Get feedback from navigation state
    const stateFeedback = location.state?.feedback;
    
    if (stateFeedback) {
      setFeedback(stateFeedback);
      // Try to extract student name from feedback
      const nameMatch = stateFeedback.match(/Hi (\w+),/i);
      if (nameMatch) {
        setStudentName(nameMatch[1]);
      }
      setLoading(false);
    } else {
      // Try localStorage as fallback
      const savedFeedback = localStorage.getItem('lastFeedback');
      if (savedFeedback) {
        setFeedback(savedFeedback);
        const nameMatch = savedFeedback.match(/Hi (\w+),/i);
        if (nameMatch) {
          setStudentName(nameMatch[1]);
        }
      }
      setLoading(false);
    }
  }, [location.state]);

  const downloadFeedback = () => {
    const element = document.createElement("a");
    const file = new Blob([feedback], { type: 'text/plain' });
    element.href = URL.createObjectURL(file);
    element.download = `feedback-${studentName || 'session'}-${new Date().toISOString().split('T')[0]}.txt`;
    document.body.appendChild(element);
    element.click();
    document.body.removeChild(element);
  };

  const shareFeedback = () => {
    if (navigator.share) {
      navigator.share({
        title: `Feedback for ${studentName || 'Session'}`,
        text: feedback,
      }).catch(() => copyToClipboard());
    } else {
      copyToClipboard();
    }
  };

  const copyToClipboard = () => {
    navigator.clipboard.writeText(feedback);
    alert('✅ Feedback copied to clipboard');
  };

  // Parse feedback sections
  const parseFeedback = (text) => {
    if (!text) return null;

    // Extract sections using regex
    const greetingMatch = text.match(/Hi ([^,]+),/);
    const greeting = greetingMatch ? greetingMatch[0] : '';
    
    const strengthsMatch = text.match(/\*\*Strengths?:\*\*([\s\S]*?)(?=\*\*|$)/i);
    const improvementsMatch = text.match(/\*\*Areas? for Improvement:\*\*([\s\S]*?)(?=\*\*|$)/i);
    const nextStepsMatch = text.match(/\*\*Next Steps?:\*\*([\s\S]*?)(?=\*\*|$)/i);
    const closingMatch = text.match(/Keep up the good work[^.!]*[.!]/i);

    return {
      greeting,
      strengths: strengthsMatch ? strengthsMatch[1].trim() : '',
      improvements: improvementsMatch ? improvementsMatch[1].trim() : '',
      nextSteps: nextStepsMatch ? nextStepsMatch[1].trim() : '',
      closing: closingMatch ? closingMatch[0] : ''
    };
  };

  const parsed = parseFeedback(feedback);

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
        {/* Back Button */}
        <button
          onClick={() => navigate("/")}
          className="flex items-center gap-2 text-gray-600 hover:text-indigo-600 mb-8 transition-colors group"
        >
          <MdArrowBack className="group-hover:-translate-x-1 transition-transform" />
          <span>Back to Dashboard</span>
        </button>

        {/* Main Feedback Card */}
        <div className="bg-white rounded-2xl shadow-sm border border-gray-200 overflow-hidden">
          {/* Header */}
          <div className="px-8 py-6 border-b border-gray-200">
            <div className="flex items-center justify-between">
              <div>
                <h1 className="text-2xl font-semibold text-gray-900">Session Feedback</h1>
                <p className="text-sm text-gray-500 mt-1">
                  {studentName ? `For ${studentName}` : 'Personalized assessment'}
                </p>
              </div>
              <div className="flex items-center gap-1">
                {[1, 2, 3, 4, 5].map((star) => (
                  <MdStar key={star} className="w-5 h-5 text-yellow-400" />
                ))}
              </div>
            </div>
          </div>

          {/* Feedback Content */}
          <div className="px-8 py-6">
            {/* Greeting */}
            {parsed?.greeting && (
              <p className="text-gray-700 mb-6">{parsed.greeting}</p>
            )}

            {/* Strengths Section */}
            {parsed?.strengths && (
              <div className="mb-6">
                <h2 className="text-lg font-semibold text-gray-900 mb-3 flex items-center gap-2">
                  <span className="w-1.5 h-1.5 bg-green-500 rounded-full"></span>
                  Strengths
                </h2>
                <div className="pl-4 text-gray-700 whitespace-pre-line">
                  {parsed.strengths.split('*').map((item, i) => {
                    const trimmed = item.trim();
                    if (!trimmed) return null;
                    return (
                      <div key={i} className="flex items-start gap-2 mb-2">
                        <span className="text-gray-400 mt-1">•</span>
                        <span>{trimmed}</span>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Areas for Improvement */}
            {parsed?.improvements && (
              <div className="mb-6">
                <h2 className="text-lg font-semibold text-gray-900 mb-3 flex items-center gap-2">
                  <span className="w-1.5 h-1.5 bg-amber-500 rounded-full"></span>
                  Areas for Improvement
                </h2>
                <div className="pl-4 text-gray-700 whitespace-pre-line">
                  {parsed.improvements.split('*').map((item, i) => {
                    const trimmed = item.trim();
                    if (!trimmed) return null;
                    return (
                      <div key={i} className="flex items-start gap-2 mb-2">
                        <span className="text-gray-400 mt-1">•</span>
                        <span>{trimmed}</span>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Next Steps */}
            {parsed?.nextSteps && (
              <div className="mb-6">
                <h2 className="text-lg font-semibold text-gray-900 mb-3 flex items-center gap-2">
                  <span className="w-1.5 h-1.5 bg-blue-500 rounded-full"></span>
                  Next Steps
                </h2>
                <div className="pl-4 text-gray-700 whitespace-pre-line">
                  {parsed.nextSteps.split('*').map((item, i) => {
                    const trimmed = item.trim();
                    if (!trimmed) return null;
                    return (
                      <div key={i} className="flex items-start gap-2 mb-2">
                        <span className="text-gray-400 mt-1">•</span>
                        <span>{trimmed}</span>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Closing */}
            {parsed?.closing && (
              <p className="text-gray-700 italic mt-6 pt-4 border-t border-gray-100">
                {parsed.closing}
              </p>
            )}

            {/* If parsing fails, show raw feedback */}
            {!parsed?.greeting && !parsed?.strengths && (
              <div className="text-gray-700 whitespace-pre-line">
                {feedback}
              </div>
            )}
          </div>

          {/* Footer with Actions */}
          <div className="px-8 py-4 bg-gray-50 border-t border-gray-200 flex justify-end gap-3">
            <button
              onClick={downloadFeedback}
              className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors flex items-center gap-2"
            >
              <MdDownload className="w-4 h-4" />
              Download
            </button>
            <button
              onClick={shareFeedback}
              className="px-4 py-2 text-sm font-medium text-white bg-indigo-600 rounded-lg hover:bg-indigo-700 transition-colors flex items-center gap-2"
            >
              <MdShare className="w-4 h-4" />
              Share
            </button>
          </div>
        </div>

        {/* Simple Stats Card (Optional) */}
        <div className="mt-6 bg-white rounded-xl border border-gray-200 p-4">
          <div className="flex items-center justify-between text-sm">
            <span className="text-gray-600">Session completed</span>
            <span className="text-gray-900 font-medium">
              {new Date().toLocaleDateString('en-US', { 
                month: 'short', 
                day: 'numeric', 
                year: 'numeric' 
              })}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}