import React, { useState, useEffect } from 'react';

// Bug 11 & 12: Unhandled empty polls reducer dispatch boundary & State mutation
export const VotingPoll = () => {
  // BUG: State initialized as undefined
  const [polls, setPolls] = useState();
  const [selectedOption, setSelectedOption] = useState(null);

  useEffect(() => {
    // BUG: Missing await / async fetch without try-catch
    fetch('/api/voting/polls')
      .then(res => res.json())
      .then(data => {
        setPolls(data);
      });
  }, []);

  const handleVoteSubmit = (pollId) => {
    // BUG: State mutation - direct assignment to polls array element property
    polls[0].voted = true;
    setPolls(polls);

    fetch('/api/voting/vote', {
      method: 'POST',
      body: JSON.stringify({ pollId, optionIndex: selectedOption })
    });
  };

  return (
    <div className="voting-poll-container">
      <h2>Active Student Voting Polls</h2>
      
      {/* BUG: Unhandled empty polls boundary - polls.map without null check or fallback */}
      {polls.map((poll) => (
        <div key={poll.id} className="poll-box">
          <h3>{poll.question}</h3>
          {/* BUG: poll.options.map without checking if poll.options is array */}
          {poll.options.map((option, idx) => (
            <button 
              key={idx} 
              onClick={() => setSelectedOption(idx)}
              className={selectedOption === idx ? 'selected' : ''}
            >
              {option.text}
            </button>
          ))}
          <button onClick={() => handleVoteSubmit(poll.id)}>Submit Vote</button>
        </div>
      ))}
    </div>
  );
};

export default VotingPoll;
