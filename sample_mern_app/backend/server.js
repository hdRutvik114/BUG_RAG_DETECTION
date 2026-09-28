// Sample MERN Application - Server Entry Point
const express = require('express');
const cors = require('cors');
const attendanceRoutes = require('./controllers/attendanceController');
const votingRoutes = require('./controllers/votingController');
const authRoutes = require('./controllers/authController');

const app = express();
app.use(cors());
app.use(express.json());

app.use('/api/attendance', attendanceRoutes);
app.use('/api/voting', votingRoutes);
app.use('/api/auth', authRoutes);

const PORT = process.env.PORT || 5000;
app.listen(PORT, () => {
  console.log(`Sample MERN Voting & Attendance Server running on port ${PORT}`);
});
