// =========================
// Admin Dashboard - COMPLETELY FIXED VERSION
// =========================
import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom'; // ✅ ADD THIS IMPORT
import { 
  MdSettings, 
  MdPeople, 
  MdLink, 
  MdDelete, 
  MdRefresh, 
  MdVisibility, 
  MdContentCopy,
  MdDashboard,
  MdBarChart,
  MdHistory,
  MdSecurity,
  MdCheckCircle,
  MdWarning,
  MdEdit,
  MdCancel,
  MdSave,
  MdAdd,
  MdDownload,
  MdFileDownload,
  MdExitToApp,
  MdPlayArrow,
  MdStop,
  MdChat,
  MdPerson,
  MdGroup,
  MdPsychology, // ✅ ADDED - for Active Mode icon
  MdAutoMode  
} from 'react-icons/md';

const API_URL = process.env.REACT_APP_API_URL || 'http://localhost:5000';
const FRONTEND_URL = window.location.origin;

export default function AdminDashboard() {
  const navigate = useNavigate(); // ✅ ADD THIS LINE
  const [activeTab, setActiveTab] = useState('dashboard');
  const [rooms, setRooms] = useState([]);
  const [stats, setStats] = useState(null);
  const [settings, setSettings] = useState([]);
  const [selectedRoom, setSelectedRoom] = useState(null);
  const [loading, setLoading] = useState(false);
  const [adminLogs, setAdminLogs] = useState([]);
  const [showCreateRoomModal, setShowCreateRoomModal] = useState(false);
  const [newRoomData, setNewRoomData] = useState({
    mode: 'active',
    max_participants: 3,
    story_id: '',
    admin_note: ''
  });

  useEffect(() => {
    loadDashboardData();
    loadSettings();
    loadAdminLogs();
    
    // Event listeners for Quick Actions
    const handleTabChange = (e) => {
      setActiveTab(e.detail.tab);
    };
    
    const handleOpenCreateRoom = () => {
      setShowCreateRoomModal(true);
    };
    
    window.addEventListener('admin:changeTab', handleTabChange);
    window.addEventListener('admin:openCreateRoom', handleOpenCreateRoom);
    
    return () => {
      window.removeEventListener('admin:changeTab', handleTabChange);
      window.removeEventListener('admin:openCreateRoom', handleOpenCreateRoom);
    };
  }, []);

  const loadDashboardData = async () => {
    try {
      setLoading(true);
      const [roomsRes, statsRes] = await Promise.all([
        fetch(`${API_URL}/admin/rooms`),
        fetch(`${API_URL}/admin/stats`)
      ]);
      
      const roomsData = await roomsRes.json();
      const statsData = await statsRes.json();
      
      setRooms(roomsData.rooms || []);
      setStats(statsData);
    } catch (err) {
      console.error('Failed to load data:', err);
      alert(`Failed to load data: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const loadSettings = async () => {
    try {
      const res = await fetch(`${API_URL}/admin/settings`);
      const data = await res.json();
      setSettings(data.settings || []);
    } catch (err) {
      console.error('Failed to load settings:', err);
    }
  };

  const loadAdminLogs = async () => {
    try {
      const res = await fetch(`${API_URL}/admin/logs`);
      const data = await res.json();
      setAdminLogs(data.logs || []);
    } catch (err) {
      console.error('Failed to load admin logs:', err);
    }
  };

  const updateSetting = async (key, value) => {
    try {
      setLoading(true);
      await fetch(`${API_URL}/admin/settings/${key}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ value, updated_by: 'admin' })
      });
      await loadSettings();
      alert(`✅ Setting "${key}" updated successfully.`);
    } catch (err) {
      console.error('Failed to update setting:', err);
      alert(`❌ Failed to update setting: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const deleteRoom = async (roomId) => {
    if (!window.confirm('Are you sure you want to delete this room? This cannot be undone.')) {
      return;
    }

    try {
      const res = await fetch(`${API_URL}/admin/rooms/${roomId}`, {
        method: 'DELETE'
      });

      if (!res.ok) {
        throw new Error('Failed to delete room');
      }

      alert('✅ Room deleted successfully');
      await loadDashboardData();
      if (selectedRoom?.room?.id === roomId) {
        setSelectedRoom(null);
        setActiveTab('rooms');
      }
    } catch (err) {
      console.error('Failed to delete room:', err);
      alert(`❌ Failed to delete room: ${err.message}`);
    }
  };

  const viewRoomDetails = async (roomId) => {
    try {
      setLoading(true);
      const res = await fetch(`${API_URL}/admin/rooms/${roomId}`);
      const data = await res.json();
      setSelectedRoom(data);
      setActiveTab('room-detail');
    } catch (err) {
      console.error('Failed to load room details:', err);
      alert(`Failed to load room details: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const createAdminRoom = async () => {
    try {
      setLoading(true);
      const res = await fetch(`${API_URL}/admin/rooms`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...newRoomData,
          admin_user: 'admin'
        })
      });

      const data = await res.json();
      
      if (!res.ok) {
        throw new Error(data.error || 'Failed to create room');
      }

      alert(`✅ Room created successfully!\nRoom ID: ${data.room.id}\nShareable Link: ${FRONTEND_URL}${data.shareable_link}`);
      setShowCreateRoomModal(false);
      setNewRoomData({
        mode: 'active',
        max_participants: 3,
        story_id: '',
        admin_note: ''
      });
      await loadDashboardData();
      await loadAdminLogs();
    } catch (err) {
      console.error('Failed to create room:', err);
      alert(`❌ Failed to create room: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const exportRoomChat = async (roomId, format) => {
    try {
      const res = await fetch(`${API_URL}/admin/rooms/${roomId}/export/chat?format=${format}`);
      
      if (!res.ok) {
        const error = await res.json();
        throw new Error(error.error || 'Export failed');
      }

      if (format === 'json') {
        const data = await res.json();
        const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `chat_${roomId}_${new Date().toISOString().split('T')[0]}.json`;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);
      } else {
        const blob = await res.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = res.headers.get('Content-Disposition')?.split('filename=')[1] || `chat_${roomId}.${format}`;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);
      }

      alert(`✅ Chat exported successfully as ${format.toUpperCase()}`);
    } catch (err) {
      console.error('Export failed:', err);
      alert(`❌ Export failed: ${err.message}`);
    }
  };

  const endRoomSession = async (roomId, endType = 'session') => {
    if (!window.confirm(`Are you sure you want to end the ${endType}?`)) {
      return;
    }

    try {
      const res = await fetch(`${API_URL}/admin/rooms/${roomId}/end`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          type: endType,
          admin_user: 'admin'
        })
      });

      const data = await res.json();
      
      if (!res.ok) {
        throw new Error(data.error || 'Failed to end session');
      }

      alert(`✅ ${endType === 'story' ? 'Story' : 'Session'} ended successfully`);
      await loadDashboardData();
      if (selectedRoom?.room?.id === roomId) {
        viewRoomDetails(roomId);
      }
    } catch (err) {
      console.error('Failed to end session:', err);
      alert(`❌ Failed to end session: ${err.message}`);
    }
  };

  const updateRoomStatus = async (roomId, status) => {
    try {
      const res = await fetch(`${API_URL}/admin/rooms/${roomId}/status`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          status,
          admin_user: 'admin'
        })
      });

      const data = await res.json();
      
      if (!res.ok) {
        throw new Error(data.error || 'Failed to update status');
      }

      alert(`✅ Room status updated to ${status}`);
      await loadDashboardData();
      if (selectedRoom?.room?.id === roomId) {
        viewRoomDetails(roomId);
      }
    } catch (err) {
      console.error('Failed to update status:', err);
      alert(`❌ Failed to update status: ${err.message}`);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100">
      {/* Modern Header */}
      <header className="bg-white border-b border-gray-200 shadow-sm">
        <div className="px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-gradient-to-r from-indigo-600 to-purple-600 flex items-center justify-center">
                <MdSecurity className="text-xl text-white" />
              </div>
              <div>
                <h1 className="text-xl font-bold text-gray-900">LLM Moderator Admin</h1>
                <p className="text-sm text-gray-500">Complete Control Panel</p>
              </div>
            </div>
            <div className="flex items-center gap-4">
              <div className="hidden md:flex items-center gap-4">
                <div className="text-right">
                  <p className="text-sm font-medium text-gray-700">System Status</p>
                  <div className="flex items-center gap-1">
                    <MdCheckCircle className="text-green-500" />
                    <span className="text-sm text-green-600">All Systems Operational</span>
                  </div>
                </div>
                <button 
                  onClick={loadDashboardData}
                  disabled={loading}
                  className="btn-primary px-4 py-2 flex items-center gap-2 disabled:opacity-50"
                >
                  <MdRefresh className={`mr-2 ${loading ? 'animate-spin' : ''}`} />
                  {loading ? 'Refreshing...' : 'Refresh'}
                </button>
              </div>
            </div>
          </div>
        </div>
      </header>

      <div className="flex">
        {/* Modern Sidebar */}
        <aside className="w-64 bg-white border-r border-gray-200 min-h-[calc(100vh-5rem)]">
          <nav className="p-4 space-y-1">
            <NavItem 
              active={activeTab === 'dashboard'} 
              onClick={() => setActiveTab('dashboard')}
              icon={<MdDashboard />}
              label="Dashboard"
              badge=""
            />
            <NavItem 
              active={activeTab === 'rooms'} 
              onClick={() => setActiveTab('rooms')}
              icon={<MdPeople />}
              label="Rooms"
              badge={rooms.length}
            />
            <NavItem 
              active={activeTab === 'links'} 
              onClick={() => {
                setActiveTab('links');
                navigate('/shareable-links'); // ✅ NOW WORKS with useNavigate
              }} 
              icon={<MdLink />}
              label="Shareable Links"
              badge=""
            />
            <NavItem 
              active={activeTab === 'settings'} 
              onClick={() => setActiveTab('settings')}
              icon={<MdSettings />}
              label="Settings"
              badge=""
            />
            <NavItem 
              active={activeTab === 'logs'} 
              onClick={() => setActiveTab('logs')}
              icon={<MdHistory />}
              label="Admin Logs"
              badge={adminLogs.length}
            />
          </nav>
        </aside>

        {/* Main Content */}
        <main className="flex-1 p-6">
          {activeTab === 'dashboard' && <DashboardView stats={stats} rooms={rooms} />}
          {activeTab === 'rooms' && (
            <RoomsView 
              rooms={rooms} 
              onViewDetails={viewRoomDetails}
              onDeleteRoom={deleteRoom}
              onRefresh={loadDashboardData}
              onCreateRoom={() => setShowCreateRoomModal(true)}
              onExportChat={exportRoomChat}
              onEndSession={endRoomSession}
              onUpdateStatus={updateRoomStatus}
              loading={loading}
            />
          )}
          {activeTab === 'links' && <LinksView />}
          {activeTab === 'settings' && (
            <SettingsView 
              settings={settings}
              onUpdate={updateSetting}
              loading={loading}
            />
          )}
          {activeTab === 'room-detail' && selectedRoom && (
            <RoomDetailView 
              room={selectedRoom}
              onBack={() => setActiveTab('rooms')}
              onDelete={() => deleteRoom(selectedRoom.room?.id)}
              onExportChat={exportRoomChat}
              onEndSession={endRoomSession}
              onUpdateStatus={updateRoomStatus}
            />
          )}
          {activeTab === 'logs' && (
            <AdminLogsView logs={adminLogs} />
          )}
        </main>
      </div>

      {/* Create Room Modal */}
      {showCreateRoomModal && (
        <CreateRoomModal
          newRoomData={newRoomData}
          setNewRoomData={setNewRoomData}
          onCreate={createAdminRoom}
          onCancel={() => setShowCreateRoomModal(false)}
          loading={loading}
        />
      )}
    </div>
  );
}

// Modern Nav Item Component
function NavItem({ active, onClick, icon, label, badge }) {
  return (
    <button
      onClick={onClick}
      className={`w-full flex items-center justify-between px-4 py-3 rounded-xl transition-all duration-200 ${
        active 
          ? 'bg-gradient-to-r from-indigo-50 to-purple-50 text-indigo-600 border border-indigo-100'
          : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900'
      }`}
    >
      <div className="flex items-center gap-3">
        <div className={`p-2 rounded-lg ${active ? 'bg-indigo-100' : 'bg-gray-100'}`}>
          {React.cloneElement(icon, { className: `text-lg ${active ? 'text-indigo-600' : 'text-gray-500'}` })}
        </div>
        <span className="font-medium">{label}</span>
      </div>
      {badge !== '' && badge > 0 && (
        <span className={`px-2 py-1 text-xs rounded-full ${
          active ? 'bg-indigo-100 text-indigo-700' : 'bg-gray-100 text-gray-700'
        }`}>
          {badge}
        </span>
      )}
    </button>
  );
}

// Modern Dashboard View
function DashboardView({ stats, rooms }) {
  const activeRooms = rooms.filter(r => r.status === 'active').length;
  const waitingRooms = rooms.filter(r => r.status === 'waiting').length;
  const completedRooms = rooms.filter(r => r.status === 'completed').length;
  const totalParticipants = rooms.reduce((sum, room) => sum + (room.actual_participant_count || 0), 0);
  const uniqueUsers = new Set();
  rooms.forEach(room => {
    (room.participant_names || []).forEach(name => uniqueUsers.add(name));
  });

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <StatCard
          title="Active Rooms"
          value={activeRooms}
          icon={<MdPeople className="text-2xl" />}
          color="green"
          change={`${((activeRooms / rooms.length) * 100 || 0).toFixed(1)}%`}
        />
        <StatCard
          title="Total Participants"
          value={totalParticipants}
          icon={<MdGroup className="text-2xl" />}
          color="blue"
          change={`${uniqueUsers.size} unique`}
        />
        <StatCard
          title="Total Messages"
          value={stats?.messages?.total || 0}
          icon={<MdChat className="text-2xl" />}
          color="purple"
          change={`${stats?.messages?.messages_today || 0} today`}
        />
        <StatCard
          title="Completed Sessions"
          value={completedRooms}
          icon={<MdCheckCircle className="text-2xl" />}
          color="orange"
          change={`${((completedRooms / rooms.length) * 100 || 0).toFixed(1)}%`}
        />
      </div>

      {/* Quick Actions */}
      <div className="card p-6">
        <h3 className="text-lg font-bold text-gray-800 mb-4">Quick Actions</h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <button 
            onClick={() => {
              window.dispatchEvent(new CustomEvent('admin:changeTab', { detail: { tab: 'links' } }));
            }}
            className="p-4 bg-indigo-50 hover:bg-indigo-100 rounded-xl transition-colors text-center group"
          >
            <MdLink className="text-2xl text-indigo-600 mx-auto mb-2 group-hover:scale-110 transition-transform" />
            <span className="font-medium text-gray-700">Share Links</span>
          </button>
          
          <button 
            onClick={() => {
              window.dispatchEvent(new CustomEvent('admin:openCreateRoom'));
            }}
            className="p-4 bg-green-50 hover:bg-green-100 rounded-xl transition-colors text-center group"
          >
            <MdAdd className="text-2xl text-green-600 mx-auto mb-2 group-hover:scale-110 transition-transform" />
            <span className="font-medium text-gray-700">New Room</span>
          </button>
          
          <button 
            onClick={() => {
              const exportAllData = async () => {
                try {
                  const res = await fetch(`${API_URL}/admin/rooms`);
                  const data = await res.json();
                  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
                  const url = window.URL.createObjectURL(blob);
                  const a = document.createElement('a');
                  a.href = url;
                  a.download = `all_rooms_export_${new Date().toISOString().split('T')[0]}.json`;
                  document.body.appendChild(a);
                  a.click();
                  window.URL.revokeObjectURL(url);
                  document.body.removeChild(a);
                  alert('✅ All rooms data exported successfully');
                } catch (err) {
                  console.error('Export failed:', err);
                  alert('❌ Export failed: ' + err.message);
                }
              };
              exportAllData();
            }}
            className="p-4 bg-purple-50 hover:bg-purple-100 rounded-xl transition-colors text-center group"
          >
            <MdDownload className="text-2xl text-purple-600 mx-auto mb-2 group-hover:scale-110 transition-transform" />
            <span className="font-medium text-gray-700">Export Data</span>
          </button>
          
          <button 
            onClick={() => {
              window.dispatchEvent(new CustomEvent('admin:changeTab', { detail: { tab: 'settings' } }));
            }}
            className="p-4 bg-orange-50 hover:bg-orange-100 rounded-xl transition-colors text-center group"
          >
            <MdSettings className="text-2xl text-orange-600 mx-auto mb-2 group-hover:scale-110 transition-transform" />
            <span className="font-medium text-gray-700">Settings</span>
          </button>
        </div>
      </div>

      {/* Recent Rooms */}
      <div className="card p-6">
        <div className="flex items-center justify-between mb-6">
          <h3 className="text-lg font-bold text-gray-800">Recent Rooms</h3>
          <span className="text-sm text-gray-500">{rooms.length} total rooms</span>
        </div>
        <div className="space-y-4">
          {rooms.slice(0, 5).map((room) => (
            <div key={room.id} className="flex items-center justify-between p-4 bg-gray-50 rounded-xl hover:bg-gray-100 transition-colors">
              <div className="flex items-center gap-3">
                <div className={`w-3 h-3 rounded-full ${
                  room.status === 'active' ? 'bg-green-500' :
                  room.status === 'waiting' ? 'bg-yellow-500' : 'bg-gray-500'
                }`}></div>
                <div>
                  <p className="font-medium text-gray-800">Room: {(room.id || '').substring(0, 8)}...</p>
                  <p className="text-sm text-gray-500">
                    {room.mode || 'unknown'} mode • {room.actual_participant_count || 0} participants
                    {room.participant_names && room.participant_names.length > 0 && (
                      <span className="ml-2">({room.participant_names.slice(0, 2).join(', ')}{room.participant_names.length > 2 ? '...' : ''})</span>
                    )}
                  </p>
                </div>
              </div>
              <span className="text-sm text-gray-500">
                {room.created_at ? new Date(room.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : 'Unknown'}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* System Stats */}
      {stats && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="card p-6">
            <h3 className="text-lg font-bold text-gray-800 mb-4">Participant Stats</h3>
            <div className="space-y-3">
              <div className="flex justify-between">
                <span className="text-gray-600">Total Participants:</span>
                <span className="font-semibold">{stats.participants?.total || 0}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-600">Unique Users:</span>
                <span className="font-semibold">{stats.participants?.unique_users || 0}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-600">Today's Participants:</span>
                <span className="font-semibold">{stats.participants?.participants_today || 0}</span>
              </div>
            </div>
          </div>
          
          <div className="card p-6">
            <h3 className="text-lg font-bold text-gray-800 mb-4">Message Stats</h3>
            <div className="space-y-3">
              <div className="flex justify-between">
                <span className="text-gray-600">Total Messages:</span>
                <span className="font-semibold">{stats.messages?.total || 0}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-600">Today's Messages:</span>
                <span className="font-semibold">{stats.messages?.messages_today || 0}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-600">Chat Messages:</span>
                <span className="font-semibold">{stats.messages?.chat || 0}</span>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// Modern Stat Card Component
function StatCard({ title, value, icon, color, change }) {
  const colorClasses = {
    blue: { bg: 'bg-blue-50', text: 'text-blue-600', border: 'border-blue-100' },
    green: { bg: 'bg-green-50', text: 'text-green-600', border: 'border-green-100' },
    purple: { bg: 'bg-purple-50', text: 'text-purple-600', border: 'border-purple-100' },
    orange: { bg: 'bg-orange-50', text: 'text-orange-600', border: 'border-orange-100' }
  };

  const colors = colorClasses[color] || colorClasses.blue;

  return (
    <div className={`card p-6 border ${colors.border}`}>
      <div className="flex items-center justify-between mb-4">
        <div className={`p-3 rounded-xl ${colors.bg} ${colors.text}`}>
          {icon}
        </div>
        <span className="text-sm font-medium text-green-600 bg-green-50 px-2 py-1 rounded-full">
          {change}
        </span>
      </div>
      <h3 className="text-3xl font-bold text-gray-900 mb-2">{value}</h3>
      <p className="text-sm text-gray-600">{title}</p>
    </div>
  );
}

// Rooms List View
function RoomsView({ rooms, onViewDetails, onDeleteRoom, onRefresh, onCreateRoom, onExportChat, onEndSession, onUpdateStatus, loading }) {
  const [filter, setFilter] = useState('all');
  const [search, setSearch] = useState('');

  const filteredRooms = rooms.filter(room => {
    if (filter === 'all') return true;
    if (filter === 'active') return room.status === 'active';
    if (filter === 'waiting') return room.status === 'waiting';
    if (filter === 'completed') return room.status === 'completed';
    return true;
  }).filter(room => {
    if (!search) return true;
    const searchLower = search.toLowerCase();
    return (
      room.id.toLowerCase().includes(searchLower) ||
      (room.story_id && room.story_id.toLowerCase().includes(searchLower)) ||
      (room.participant_names && room.participant_names.some(name => 
        name.toLowerCase().includes(searchLower)
      ))
    );
  });

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <h2 className="text-2xl font-bold text-gray-800">Rooms Management</h2>
        <div className="flex gap-3">
          <button
            onClick={onCreateRoom}
            className="btn-primary flex items-center gap-2"
          >
            <MdAdd /> Create Room
          </button>
          <button
            onClick={onRefresh}
            disabled={loading}
            className="btn-secondary flex items-center gap-2"
          >
            <MdRefresh className={loading ? 'animate-spin' : ''} />
            {loading ? 'Refreshing...' : 'Refresh'}
          </button>
        </div>
      </div>

      {/* Filters and Search */}
      <div className="card p-4 mb-6">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Filter by Status</label>
            <select
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              className="border border-gray-300 rounded-lg px-4 py-2 bg-white focus:outline-none focus:ring-2 focus:ring-indigo-200 w-full"
            >
              <option value="all">All Rooms</option>
              <option value="waiting">Waiting</option>
              <option value="active">Active</option>
              <option value="completed">Completed</option>
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Search Rooms</label>
            <input
              type="text"
              placeholder="Search by ID, story, or participant..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="border border-gray-300 rounded-lg px-4 py-2 bg-white focus:outline-none focus:ring-2 focus:ring-indigo-200 w-full"
            />
          </div>
        </div>
      </div>

      {filteredRooms.length === 0 ? (
        <div className="card p-12 text-center">
          <div className="w-20 h-20 rounded-full bg-gray-100 flex items-center justify-center mx-auto mb-4">
            <MdPeople className="text-3xl text-gray-400" />
          </div>
          <p className="text-gray-500 text-lg">No rooms found</p>
          <p className="text-gray-400 mt-2">Try changing your filter or create a new room</p>
          <button
            onClick={onCreateRoom}
            className="mt-4 btn-primary"
          >
            <MdAdd className="mr-2" /> Create First Room
          </button>
        </div>
      ) : (
        <div className="card overflow-hidden">
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Room ID</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Mode</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Status</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Participants</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Created</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Actions</th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {filteredRooms.map((room) => (
                  <tr key={room.id} className="hover:bg-gray-50 transition-colors">
                    <td className="px-6 py-4">
                      <div className="text-sm font-mono text-gray-900">{(room.id || '').substring(0, 10)}...</div>
                      <div className="text-xs text-gray-500 truncate max-w-xs">
                        Story: {room.story_id || 'default'}
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      <span className={`px-3 py-1 rounded-full text-xs font-medium ${
                        room.mode === 'active' 
                          ? 'bg-blue-100 text-blue-800' 
                          : 'bg-purple-100 text-purple-800'
                      }`}>
                        {room.mode || 'unknown'}
                      </span>
                    </td>
                    <td className="px-6 py-4">
                      <span className={`px-3 py-1 rounded-full text-xs font-medium ${
                        room.status === 'active' ? 'bg-green-100 text-green-800' :
                        room.status === 'waiting' ? 'bg-yellow-100 text-yellow-800' :
                        'bg-gray-100 text-gray-800'
                      }`}>
                        {room.status || 'unknown'}
                      </span>
                    </td>
                    <td className="px-6 py-4">
                      <div className="space-y-2">
                        <div className="flex items-center gap-2">
                          <span className="text-sm text-gray-900">
                            {room.actual_participant_count || 0} / {room.max_participants || 3}
                          </span>
                          <div className="w-16 bg-gray-200 rounded-full h-2">
                            <div 
                              className="bg-green-500 h-2 rounded-full"
                              style={{ 
                                width: `${((room.actual_participant_count || 0) / (room.max_participants || 3)) * 100}%`,
                                maxWidth: '100%'
                              }}
                            ></div>
                          </div>
                        </div>
                        {room.participant_names && room.participant_names.length > 0 && (
                          <div className="text-xs text-gray-500 truncate max-w-xs">
                            {room.participant_names.slice(0, 3).join(', ')}
                            {room.participant_names.length > 3 && '...'}
                          </div>
                        )}
                      </div>
                    </td>
                    <td className="px-6 py-4 text-sm text-gray-500">
                      {room.created_at ? new Date(room.created_at).toLocaleDateString() : 'Unknown'}
                    </td>
                    <td className="px-6 py-4">
                      <div className="flex flex-wrap gap-2">
                        <button
                          onClick={() => onViewDetails(room.id)}
                          className="flex items-center gap-1 px-3 py-1.5 bg-indigo-50 text-indigo-700 rounded-lg hover:bg-indigo-100 transition-colors text-sm"
                          title="View Details"
                        >
                          <MdVisibility size={14} />
                        </button>
                        <button
                          onClick={() => onExportChat(room.id, 'json')}
                          className="flex items-center gap-1 px-3 py-1.5 bg-green-50 text-green-700 rounded-lg hover:bg-green-100 transition-colors text-sm"
                          title="Export Chat"
                        >
                          <MdDownload size={14} />
                        </button>
                        <button
                          onClick={() => onEndSession(room.id, 'session')}
                          className="flex items-center gap-1 px-3 py-1.5 bg-red-50 text-red-700 rounded-lg hover:bg-red-100 transition-colors text-sm"
                          title="End Session"
                        >
                          <MdStop size={14} />
                        </button>
                        <button
                          onClick={() => onDeleteRoom(room.id)}
                          className="flex items-center gap-1 px-3 py-1.5 bg-gray-50 text-gray-700 rounded-lg hover:bg-gray-100 transition-colors text-sm"
                          title="Delete Room"
                        >
                          <MdDelete size={14} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

// Create Room Modal Component
function CreateRoomModal({ newRoomData, setNewRoomData, onCreate, onCancel, loading }) {
  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
      <div className="bg-white rounded-2xl shadow-2xl max-w-md w-full">
        <div className="p-6">
          <h3 className="text-xl font-bold text-gray-800 mb-4">Create New Room</h3>
          
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Mode
              </label>
              <select
                value={newRoomData.mode}
                onChange={(e) => setNewRoomData({...newRoomData, mode: e.target.value})}
                className="border border-gray-300 rounded-lg px-4 py-2 bg-white focus:outline-none focus:ring-2 focus:ring-indigo-200 w-full"
              >
                <option value="active">Active (AI Moderated)</option>
                <option value="passive">Passive (Auto-progress)</option>
              </select>
            </div>
            
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Max Participants
              </label>
              <input
                type="number"
                min="1"
                max="10"
                value={newRoomData.max_participants}
                onChange={(e) => setNewRoomData({...newRoomData, max_participants: parseInt(e.target.value)})}
                className="border border-gray-300 rounded-lg px-4 py-2 bg-white focus:outline-none focus:ring-2 focus:ring-indigo-200 w-full"
              />
            </div>
            
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Story ID (Optional)
              </label>
              <input
                type="text"
                placeholder="Leave empty for random story"
                value={newRoomData.story_id}
                onChange={(e) => setNewRoomData({...newRoomData, story_id: e.target.value})}
                className="border border-gray-300 rounded-lg px-4 py-2 bg-white focus:outline-none focus:ring-2 focus:ring-indigo-200 w-full"
              />
            </div>
            
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Admin Note (Optional)
              </label>
              <textarea
                rows="2"
                placeholder="Add a note for this room..."
                value={newRoomData.admin_note}
                onChange={(e) => setNewRoomData({...newRoomData, admin_note: e.target.value})}
                className="border border-gray-300 rounded-lg px-4 py-2 bg-white focus:outline-none focus:ring-2 focus:ring-indigo-200 w-full resize-none"
              />
            </div>
          </div>
          
          <div className="flex gap-3 mt-6">
            <button
              onClick={onCancel}
              className="flex-1 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 transition-colors"
              disabled={loading}
            >
              Cancel
            </button>
            <button
              onClick={onCreate}
              disabled={loading}
              className="flex-1 py-2 bg-gradient-to-r from-indigo-600 to-purple-600 text-white rounded-lg hover:from-indigo-700 hover:to-purple-700 transition-all disabled:opacity-50"
            >
              {loading ? 'Creating...' : 'Create Room'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// Room Detail View
function RoomDetailView({ room, onBack, onDelete, onExportChat, onEndSession, onUpdateStatus }) {
  const safeRoom = room || {};
  const safeRoomData = safeRoom.room || {};
  const safeStats = safeRoom.stats || {};
  const safeParticipants = safeRoom.participants || [];
  const safeMessages = safeRoom.messages || [];

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <button
          onClick={onBack}
          className="flex items-center gap-2 text-indigo-600 hover:text-indigo-900 font-medium"
        >
          ← Back to Rooms
        </button>
        <div className="flex gap-2">
          <button
            onClick={() => onDelete(safeRoomData.id)}
            className="flex items-center gap-2 bg-red-600 text-white px-4 py-2 rounded-lg hover:bg-red-700 transition-colors"
          >
            <MdDelete /> Delete Room
          </button>
        </div>
      </div>

      <div className="card p-6 mb-6">
        <h2 className="text-2xl font-bold mb-6">Room Details</h2>
        
        {/* Room Info Header */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
          <div className="bg-gray-50 p-4 rounded-xl">
            <p className="text-sm text-gray-600 mb-1">Room ID</p>
            <p className="font-mono text-sm break-all">{safeRoomData.id || 'N/A'}</p>
          </div>
          <div className="bg-gray-50 p-4 rounded-xl">
            <p className="text-sm text-gray-600 mb-1">Mode</p>
            <p className="font-semibold capitalize">{safeRoomData.mode || 'unknown'}</p>
          </div>
          <div className="bg-gray-50 p-4 rounded-xl">
            <p className="text-sm text-gray-600 mb-1">Status</p>
            <div className="flex items-center gap-2">
              <span className={`px-3 py-1 rounded-full text-xs font-medium ${
                safeRoomData.status === 'active' ? 'bg-green-100 text-green-800' :
                safeRoomData.status === 'waiting' ? 'bg-yellow-100 text-yellow-800' :
                'bg-gray-100 text-gray-800'
              }`}>
                {safeRoomData.status || 'unknown'}
              </span>
              {safeRoomData.story_finished && (
                <span className="px-2 py-1 bg-purple-100 text-purple-800 text-xs rounded-full">
                  Story Ended
                </span>
              )}
            </div>
          </div>
          <div className="bg-gray-50 p-4 rounded-xl">
            <p className="text-sm text-gray-600 mb-1">Story</p>
            <p className="font-medium truncate">{safeRoomData.story_id || 'default'}</p>
          </div>
        </div>

        {/* Action Buttons */}
        <div className="flex flex-wrap gap-3 mb-8">
          <div className="flex gap-2">
            <button
              onClick={() => onExportChat(safeRoomData.id, 'json')}
              className="flex items-center gap-2 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors"
            >
              <MdDownload /> Export JSON
            </button>
            <button
              onClick={() => onExportChat(safeRoomData.id, 'csv')}
              className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
            >
              <MdFileDownload /> Export CSV
            </button>
            <button
              onClick={() => onExportChat(safeRoomData.id, 'tsv')}
              className="flex items-center gap-2 px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition-colors"
            >
              <MdFileDownload /> Export TSV
            </button>
          </div>
          
          <div className="flex gap-2">
            {safeRoomData.status === 'active' && !safeRoomData.story_finished && (
              <button
                onClick={() => onEndSession(safeRoomData.id, 'story')}
                className="flex items-center gap-2 px-4 py-2 bg-orange-600 text-white rounded-lg hover:bg-orange-700 transition-colors"
              >
                <MdStop /> End Story Only
              </button>
            )}
            {safeRoomData.status === 'active' && (
              <button
                onClick={() => onEndSession(safeRoomData.id, 'session')}
                className="flex items-center gap-2 px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors"
              >
                <MdExitToApp /> End Session
              </button>
            )}
          </div>
          
          <div className="flex gap-2">
            <select
              onChange={(e) => onUpdateStatus(safeRoomData.id, e.target.value)}
              value={safeRoomData.status || ''}
              className="border border-gray-300 rounded-lg px-3 py-2 bg-white focus:outline-none focus:ring-2 focus:ring-indigo-200"
            >
              <option value="waiting">Waiting</option>
              <option value="active">Active</option>
              <option value="completed">Completed</option>
            </select>
          </div>
        </div>

        {/* Stats Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 mb-8">
          <div className="bg-gradient-to-br from-blue-50 to-blue-100 p-6 rounded-2xl">
            <div className="flex items-center justify-between mb-2">
              <MdPeople className="text-2xl text-blue-600" />
              <span className="text-3xl font-bold text-blue-700">{safeStats.participant_count || 0}</span>
            </div>
            <h4 className="font-semibold text-blue-900">Participants</h4>
          </div>
          <div className="bg-gradient-to-br from-green-50 to-green-100 p-6 rounded-2xl">
            <div className="flex items-center justify-between mb-2">
              <MdChat className="text-2xl text-green-600" />
              <span className="text-3xl font-bold text-green-700">{safeStats.message_count || 0}</span>
            </div>
            <h4 className="font-semibold text-green-900">Messages</h4>
          </div>
          <div className="bg-gradient-to-br from-purple-50 to-purple-100 p-6 rounded-2xl">
            <div className="flex items-center justify-between mb-2">
              <MdHistory className="text-2xl text-purple-600" />
              <span className="text-3xl font-bold text-purple-700">{safeStats.session_count || 0}</span>
            </div>
            <h4 className="font-semibold text-purple-900">Sessions</h4>
          </div>
        </div>

        {/* Participants Section */}
        <div className="mb-8">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold flex items-center gap-2">
              <MdPeople /> Participants ({safeParticipants.length})
            </h3>
          </div>
          <div className="space-y-3">
            {safeParticipants.length > 0 ? (
              safeParticipants.map((p, index) => (
                <div key={p?.id || index} className="flex justify-between items-center bg-gray-50 p-4 rounded-xl hover:bg-gray-100 transition-colors">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-full bg-gradient-to-r from-indigo-400 to-purple-400 flex items-center justify-center text-white font-semibold">
                      {(p?.display_name || p?.username || 'U').charAt(0).toUpperCase()}
                    </div>
                    <div>
                      <span className="font-medium">{p?.display_name || p?.username || 'Anonymous User'}</span>
                      <p className="text-xs text-gray-500">
                        Username: {p?.username || 'N/A'} • 
                        ID: {p?.id ? p.id.substring(0, 8) + '...' : 'N/A'}
                      </p>
                    </div>
                  </div>
                  <span className="text-sm text-gray-500">
                    {p?.joined_at ? new Date(p.joined_at).toLocaleTimeString() : 'Unknown'}
                  </span>
                </div>
              ))
            ) : (
              <div className="text-center py-6 text-gray-500 bg-gray-50 rounded-xl">
                No participants found
              </div>
            )}
          </div>
        </div>

        {/* Messages Section */}
        <div>
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold flex items-center gap-2">
              <MdChat /> Conversation ({safeMessages.length} messages)
            </h3>
          </div>
          <div className="bg-gray-50 rounded-2xl p-4 max-h-96 overflow-y-auto">
            {safeMessages.length > 0 ? (
              safeMessages.map((msg, idx) => {
                const username = msg?.username || msg?.sender || 'Unknown';
                const message = msg?.message || msg?.message_text || 'No message content';
                const isModerator = username.toLowerCase() === 'moderator';
                const timestamp = msg?.created_at ? new Date(msg.created_at).toLocaleTimeString([], { 
                  hour: '2-digit', 
                  minute: '2-digit',
                  second: '2-digit'
                }) : '';
                
                return (
                  <div
                    key={idx}
                    className={`mb-4 p-4 rounded-xl ${
                      isModerator 
                        ? 'bg-gradient-to-r from-amber-50 to-yellow-50 border border-amber-100' 
                        : 'bg-white border border-gray-200'
                    }`}
                  >
                    <div className="flex justify-between items-start mb-2">
                      <div className="flex items-center gap-2">
                        <div className={`w-8 h-8 rounded-full flex items-center justify-center text-white text-sm font-semibold ${
                          isModerator 
                            ? 'bg-gradient-to-r from-amber-500 to-orange-500' 
                            : 'bg-gradient-to-r from-indigo-500 to-blue-500'
                        }`}>
                          {username.charAt(0).toUpperCase()}
                        </div>
                        <div>
                          <span className="font-semibold text-sm">{username}</span>
                          {msg?.message_type && (
                            <span className="ml-2 px-1.5 py-0.5 bg-gray-100 text-gray-600 text-xs rounded">
                              {msg.message_type}
                            </span>
                          )}
                        </div>
                      </div>
                      <span className="text-xs text-gray-500">
                        {timestamp}
                      </span>
                    </div>
                    <p className="text-sm text-gray-700 whitespace-pre-wrap">{message}</p>
                  </div>
                );
              })
            ) : (
              <div className="text-center py-8 text-gray-500">
                <MdChat className="text-4xl mx-auto mb-3 text-gray-400" />
                No messages in this conversation
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// Admin Logs View Component
function AdminLogsView({ logs }) {
  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <h2 className="text-2xl font-bold text-gray-800">Admin Activity Logs</h2>
        <span className="text-sm text-gray-500">{logs.length} log entries</span>
      </div>
      
      <div className="card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Time</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Action</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Admin User</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Entity</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Details</th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {logs.map((log, index) => (
                <tr key={index} className="hover:bg-gray-50 transition-colors">
                  <td className="px-6 py-4">
                    <div className="text-sm text-gray-900">
                      {log.created_at ? new Date(log.created_at).toLocaleString() : 'Unknown'}
                    </div>
                  </td>
                  <td className="px-6 py-4">
                    <span className="px-2 py-1 bg-blue-100 text-blue-800 text-xs rounded-full">
                      {log.action}
                    </span>
                  </td>
                  <td className="px-6 py-4">
                    <div className="text-sm text-gray-900">{log.admin_user || 'system'}</div>
                  </td>
                  <td className="px-6 py-4">
                    <div className="text-sm text-gray-900">
                      {log.entity_type}: {log.entity_id ? log.entity_id.substring(0, 8) + '...' : 'N/A'}
                    </div>
                  </td>
                  <td className="px-6 py-4">
                    <div className="text-xs text-gray-500 max-w-xs truncate">
                      {JSON.stringify(log.details || {})}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

// Links View
function LinksView() {
  const activeLink = `${FRONTEND_URL}/join/active`;
  const passiveLink = `${FRONTEND_URL}/join/passive`;

  const copyToClipboard = (text, type) => {
    navigator.clipboard.writeText(text);
    alert(`✅ ${type} link copied to clipboard!`);
  };

  return (
    <div className="bg-white rounded-2xl shadow-xl p-8">
      <div className="text-center mb-6">
        <h2 className="text-3xl font-bold text-gray-800 mb-2">Quick Join Links</h2>
        <p className="text-gray-600">Share these links with participants for instant access</p>
      </div>

      <div className="space-y-4">
        {/* Active Mode Link */}
        <div className="border-2 border-indigo-200 rounded-xl p-4 hover:border-indigo-400 transition">
          <div className="flex items-center mb-2">
            <MdPsychology className="text-2xl text-indigo-600 mr-2" />
            <h3 className="text-lg font-semibold text-gray-800">Active Mode</h3>
          </div>
          <p className="text-sm text-gray-600 mb-3">AI actively engages and asks questions</p>
          <div className="flex items-center gap-2">
            <input
              type="text"
              value={activeLink}
              readOnly
              className="flex-1 px-3 py-2 border border-gray-300 rounded-lg bg-gray-50 text-sm font-mono"
            />
            <button
              onClick={() => copyToClipboard(activeLink, 'Active mode')}
              className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition flex items-center gap-2"
            >
              <MdContentCopy className="text-xl" /> Copy
            </button>
          </div>
        </div>

        {/* Passive Mode Link */}
        <div className="border-2 border-purple-200 rounded-xl p-4 hover:border-purple-400 transition">
          <div className="flex items-center mb-2">
            <MdAutoMode className="text-2xl text-purple-600 mr-2" />
            <h3 className="text-lg font-semibold text-gray-800">Passive Mode</h3>
          </div>
          <p className="text-sm text-gray-600 mb-3">Story auto-advances at intervals</p>
          <div className="flex items-center gap-2">
            <input
              type="text"
              value={passiveLink}
              readOnly
              className="flex-1 px-3 py-2 border border-gray-300 rounded-lg bg-gray-50 text-sm font-mono"
            />
            <button
              onClick={() => copyToClipboard(passiveLink, 'Passive mode')}
              className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition flex items-center gap-2"
            >
              <MdContentCopy className="text-xl" /> Copy
            </button>
          </div>
        </div>
      </div>

      <div className="mt-6 p-4 bg-blue-50 rounded-lg">
        <h4 className="font-semibold text-gray-800 mb-2">📋 How it works:</h4>
        <ul className="text-sm text-gray-700 space-y-1">
          <li>• Participants click the link to join automatically</li>
          <li>• Max 3 participants per room</li>
          <li>• New rooms created automatically when full</li>
          <li>• No signup or login required</li>
        </ul>
      </div>
    </div>
  );
}

// Settings View (simplified)
function SettingsView({ settings, onUpdate, loading }) {
  const [editingKey, setEditingKey] = useState(null);
  const [editValue, setEditValue] = useState('');

  const startEdit = (key, currentValue) => {
    setEditingKey(key);
    setEditValue(currentValue);
  };

  const saveEdit = async () => {
    if (editingKey) {
      await onUpdate(editingKey, editValue);
      setEditingKey(null);
    }
  };

  const cancelEdit = () => {
    setEditingKey(null);
  };

  return (
    <div>
      <h2 className="text-2xl font-bold text-gray-800 mb-6">System Settings</h2>
      
      <div className="card p-6">
        <div className="space-y-4">
          {settings.map((setting) => (
            <div key={setting.key} className="border-b border-gray-200 pb-4 last:border-0">
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <h3 className="font-semibold text-gray-800">{setting.key}</h3>
                  <p className="text-sm text-gray-600">{setting.description || ''}</p>
                  
                  {editingKey === setting.key ? (
                    <div className="mt-2 flex gap-2">
                      <input
                        type="text"
                        value={editValue}
                        onChange={(e) => setEditValue(e.target.value)}
                        className="flex-1 border border-gray-300 rounded-lg px-3 py-1 text-sm"
                        autoFocus
                      />
                      <button
                        onClick={saveEdit}
                        className="p-1 bg-green-100 text-green-700 rounded hover:bg-green-200"
                        disabled={loading}
                      >
                        <MdSave size={18} />
                      </button>
                      <button
                        onClick={cancelEdit}
                        className="p-1 bg-red-100 text-red-700 rounded hover:bg-red-200"
                      >
                        <MdCancel size={18} />
                      </button>
                    </div>
                  ) : (
                    <div className="mt-1 flex items-center gap-2">
                      <span className="text-sm font-mono bg-gray-100 px-2 py-1 rounded">
                        {setting.value}
                      </span>
                      <span className="text-xs text-gray-500">({setting.data_type})</span>
                    </div>
                  )}
                </div>
                
                {editingKey !== setting.key && (
                  <button
                    onClick={() => startEdit(setting.key, setting.value)}
                    className="p-2 text-gray-600 hover:text-indigo-600 hover:bg-indigo-50 rounded-lg transition-colors"
                  >
                    <MdEdit size={18} />
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}