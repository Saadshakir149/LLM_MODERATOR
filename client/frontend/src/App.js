// =========================
// path: src/App.jsx - FIXED VERSION
// =========================
import React from 'react';
import { BrowserRouter as Router, Route, Routes } from 'react-router-dom';
import RoomCreation from './components/RoomCreation';
import ChatRoom from './components/ChatRoom';
import FeedbackPage from './components/FeedbackPage';
import AutoJoin from './components/AutoJoin';
import AdminDashboard from './components/AdminDashboard';
import ShareableLinks from './components/ShareableLinks'; // ✅ ADD THIS IMPORT

export default function App() {
  return (
    <Router>
      <Routes>
        <Route path="/" element={<RoomCreation />} />
        <Route path="/join/:mode" element={<AutoJoin />} />
        <Route path="/chat/:roomId" element={<ChatRoom />} />
        <Route path="/feedback" element={<FeedbackPage />} />
        <Route path="/admin" element={<AdminDashboard />} />
        {/* ✅ ADD THIS ROUTE */}
        <Route path="/shareable-links" element={<ShareableLinks />} />
      </Routes>
    </Router>
  );
}