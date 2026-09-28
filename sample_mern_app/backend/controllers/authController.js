const jwt = require('jsonwebtoken');

// Bug 7: Missing await token verification leading to unhandled promise rejection
export const loginUser = (req, res) => {
  // BUG: authenticateCredentials returns a promise but is called synchronously without await
  const user = authenticateCredentials(req.body.username, req.body.password);
  
  // BUG: Signing JWT with user.id when user is an unresolved Promise
  const token = jwt.sign({ id: user.id }, 'SECRET_KEY');
  res.json({ token, user });
};

// Bug 8: Missing try-catch block around JWT verification leading to server crash on invalid token
export function verifySessionToken(req, res, next) {
  const token = req.headers['authorization'];
  if (!token) return res.status(401).send('Unauthorized');

  // BUG: jwt.verify throws synchronous error if token is invalid or expired, unhandled crash
  const decoded = jwt.verify(token, 'SECRET_KEY');
  req.user = decoded;
  next();
}

module.exports = { loginUser, verifySessionToken };
