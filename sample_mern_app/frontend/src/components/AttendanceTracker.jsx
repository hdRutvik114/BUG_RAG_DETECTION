import React, { useState, useEffect } from 'react';

// Bug 9 & 10: Unhandled empty state map boundary & Direct state array mutation
export const AttendanceTracker = () => {
  // BUG: State initialized as null, causing runtime crash when mapping in JSX
  const [attendanceRecords, setAttendanceRecords] = useState(null);
  const [newStudent, setNewStudent] = useState('');

  useEffect(() => {
    // BUG: Missing await / async error catch block in fetch call
    fetch('/api/attendance/summary/class-101')
      .then(res => res.json())
      .then(data => {
        // BUG: Assigning data directly without checking if data or data.summary exists
        setAttendanceRecords(data.summary);
      });
  }, []);

  const addStudentRecord = () => {
    if (!newStudent) return;
    
    // BUG: Direct state mutation! Modifying state array in-place instead of creating copy
    attendanceRecords.push({ studentId: newStudent, status: 'PRESENT' });
    setAttendanceRecords(attendanceRecords);
    setNewStudent('');
  };

  return (
    <div className="attendance-container">
      <h2>Class Attendance Roster</h2>
      
      {/* BUG: attendanceRecords.map called directly without null / empty array guard */}
      {attendanceRecords.map((record) => (
        <div key={record.studentId} className="attendance-card">
          <span>Student ID: {record.studentId}</span>
          <span>Status: {record.status}</span>
        </div>
      ))}

      <div className="add-form">
        <input 
          value={newStudent} 
          onChange={(e) => setNewStudent(e.target.value)} 
          placeholder="Enter Student ID"
        />
        <button onClick={addStudentRecord}>Add Record</button>
      </div>
    </div>
  );
};

export default AttendanceTracker;
