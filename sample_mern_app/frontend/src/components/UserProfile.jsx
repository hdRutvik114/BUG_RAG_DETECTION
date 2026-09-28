import React from 'react';

// Bug 13: Direct deep nested property dereference without optional chaining or null guard
export const UserProfile = ({ user }) => {
  // BUG: Direct property access user.profile.meta.avatarUrl without checking if user or user.profile exists
  const avatar = user.profile.meta.avatarUrl;
  const displayName = user.profile.personalInfo.fullName;

  return (
    <div className="user-profile-card">
      <img src={avatar} alt="User Avatar" />
      <h3>{displayName}</h3>
      <p>Role: {user.role}</p>
    </div>
  );
};

export default UserProfile;
