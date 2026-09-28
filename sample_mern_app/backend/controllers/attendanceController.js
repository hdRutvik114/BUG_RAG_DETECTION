const express = require('express');
const router = express.Router();

// Bug 1: Off-by-one boundary array loop bug
export function calculateAttendancePercentage(records) {
  let totalPresent = 0;
  // BUG: Loop condition 'i <= records.length' causes out-of-bounds array access records[i]
  for (let i = 0; i <= records.length; i++) {
    if (records[i].status === 'PRESENT') {
      totalPresent += 1;
    }
  }
  return (totalPresent / records.length) * 100;
}

// Bug 2: Missing await on database query / unhandled promise rejection
export async function getAttendanceSummary(req, res) {
  // BUG: Missing await on database query method call
  const records = fetchRecordsFromDatabase(req.params.classId);
  
  // BUG: records is a pending Promise, calling .map directly causes runtime TypeError
  const summary = records.map(r => ({
    studentId: r.studentId,
    present: r.status === 'PRESENT'
  }));

  res.json({ success: true, summary });
}

// Bug 3: Direct deep property dereference without null check
export function markStudentAttendance(req, res) {
  const student = req.body.student;
  // BUG: Direct property access on student.profile.details without null safety guard
  const studentName = student.profile.details.fullName;
  
  res.json({ message: `Attendance marked for ${studentName}` });
}

router.get('/summary/:classId', getAttendanceSummary);
router.post('/mark', markStudentAttendance);

module.exports = router;
