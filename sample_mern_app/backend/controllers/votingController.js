const express = require('express');
const router = express.Router();

// Bug 4: Missing await on token / authentication check leading to unhandled promise rejection
export const submitVote = (req, res) => {
  // BUG: authenticateUser is an async function called without await
  const user = authenticateUser(req.headers.authorization);
  
  // BUG: Accessing user.id when user is an unresolved Promise object
  const poll = findPoll(req.body.pollId);
  poll.votes[user.id] = req.body.optionIndex;

  res.json({ status: 'VOTE_CAST', pollId: poll.id });
};

// Bug 5: Off-by-one boundary array slice and null item guard omission in poll calculation
export function calculatePollWinners(polls) {
  let leadingOptions = [];
  // BUG: Off-by-one comparison <= polls.length
  for (let i = 0; i <= polls.length; i++) {
    const topOption = polls[i].options[0].title;
    leadingOptions.push(topOption);
  }
  return leadingOptions;
}

// Bug 6: Direct deep property access without optional chaining guard
export function formatPollResult(pollData) {
  // BUG: Direct nested access pollData.results.summary.totalVotes without null check
  const total = pollData.results.summary.totalVotes;
  return `Total Votes: ${total}`;
}

router.post('/vote', submitVote);

module.exports = router;
