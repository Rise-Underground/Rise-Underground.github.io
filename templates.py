"""
Tweet copy templates for the Leaders of the Leaderboards competition,
normalized from UDG_X_Copy_LofL (1).docx.

Fixes applied vs. the original draft:
  - {the_Leaderboard} / {The_Leaderboard} -> {leaderboard_url} everywhere,
    to match the placeholder name actually declared in the doc.
  - Markdown bold (**text**) stripped -- X does not render markdown, so
    literal asterisks would show up in the live post.
  - "3rd Sunday of [Month]" (section 6) -> dynamic date computed from
    competition_window.py, since the real rule is now 2nd Sunday.
  - Trailing backslash line-break markers converted to real newlines.

Each category is a list of template strings (for those with multiple
variations, used for rotation). Fill with str.format(**data).
"""

# ---------------------------------------------------------------------
# 1. Pre-competition countdown -- one distinct post per day, 7 days out
#    through 1 day out. Indexed by days_remaining (7 down to 1).
# ---------------------------------------------------------------------
COUNTDOWN = {
    7: (
        "🔥 DAY 7 🔥\n\n"
        "In the Shadow of Darkness, the first signs of RISE begin.\n\n"
        "The challenge is set.\n"
        "The rankings are waiting.\n"
        "Every point matters.\n\n"
        "Calido Valley Raceway\n"
        "AeroTrails\n"
        "Holocaches\n\n"
        "The journey begins... Where will you stand?"
    ),
    6: (
        "🔥 DAY 6 🔥\n\n"
        "The shadows grow deeper... and the competition grows stronger.\n\n"
        "Every Race.\n"
        "Every AeroTrail.\n"
        "Every Holocache.\n\n"
        "Every point brings you closer to the top.\n\n"
        "📣 The Leaderboard is taking shape.\n\n"
        "Will you RISE above the rest?"
    ),
    5: (
        "🔥 DAY 5 🔥\n\n"
        "The climb has begun.\n\n"
        "Champions aren't made by one victory.\n"
        "They're built point by point.\n\n"
        "Race Your Vehicles\n"
        "Fly the AeroTrails\n"
        "Collect Holocaches\n"
        "RISE, Be the LEADER.\n\n"
        "The leaderboard is watching."
    ),
    4: (
        "🔥 DAY 4 🔥\n\n"
        "The shadows are closing in.\n\n"
        "Halfway there... but the battle is far from over.\n\n"
        "Every Calido Valley Race.\n"
        "Every AeroTrail Flight.\n"
        "Every Holocache Run.\n\n"
        "One point could change everything.\n\n"
        "🔥 Who has what it takes to RISE?"
    ),
    3: (
        "🔥 DAY 3 🔥\n\n"
        "Few Remaining Days.\n\n"
        "The gap is closing.\n"
        "The rankings are shifting.\n"
        "The pressure is rising.\n\n"
        "This is your chance to make your mark before the end draws near.\n\n"
        "📣 RISE Underground — Leaders of the Leaderboards"
    ),
    2: (
        "🔥 DAY 2 🔥\n\n"
        "The darkness is almost behind us.\n\n"
        "⚠️ ONLY 2 DAYS REMAIN.\n\n"
        "One last push.\n"
        "One last climb.\n"
        "One last chance to change your position.\n\n"
        "🏆 The ultimate ranking is almost complete.\n\n"
        "Will you RISE?"
    ),
    1: (
        "🔥 DAY 1 🔥\n\n"
        "THIS IS IT.\n\n"
        "The countdown ends today.\n\n"
        "🔥 THE FINAL DAY TO RISE. 🔥\n\n"
        "Every Calido Valley Raceway run, every AeroTrail, every Holocache "
        "counts toward one ultimate ranking.\n\n"
        "🏆 LEADERS OF THE LEADERBOARDS\n\n"
        "No tomorrow. No second chances.\n\n"
        "Where do you rank?"
    ),
}

# ---------------------------------------------------------------------
# 2. Competition opens -- single post, fired once at start
# ---------------------------------------------------------------------
COMPETITION_OPENS = (
    "🔥THE WAIT IS OVER🔥\n\n"
    "The shadows have opened.\n\n"
    "RISE UNDERGROUND PRESENTS:\n"
    "LEADERS OF THE LEADERBOARDS\n\n"
    "🚨COMPETITION IS NOW OPEN🚨\n\n"
    "📣 {leaderboard_url} 📣\n\n"
    "Calido Valley Raceway\n"
    "Aero Trails\n"
    "Holocache\n\n"
    "Every point counts. ONE ULTIMATE RANKING.\n\n"
    "STEP INTO THE SHADOWS. RISE."
)

# ---------------------------------------------------------------------
# 3. Leaderboard update templates -- 12 variations, rotate through them
#    twice a day, days 1-6 of the competition (not the final day).
#    Placeholders: top1_name, top1_points, top2_name, top2_points,
#    top3_name, top3_points, days_remaining, leaderboard_url
# ---------------------------------------------------------------------
LEADERBOARD_UPDATES = [
    (
        "LEADERS OF THE LEADERBOARDS\n\n"
        "🏆 COMPETITION IS LIVE NOW 🏆\n\n"
        "Where do you stand on the leaderboards?\n\n"
        "Choose your vehicle. Race your track. Push your limits.\n\n"
        "🏁 {leaderboard_url}\n\n"
        "The race is on. Will you rise to the top?"
    ),
    (
        "LEADERS OF THE LEADERBOARDS\n\n"
        "🏆 THE COMPETITION IS ON 🏆\n\n"
        "How high can you climb the leaderboards?\n\n"
        "Choose your vehicle. Take on your track. Chase the fastest times.\n\n"
        "🏁 {leaderboard_url}\n\n"
        "The race is underway. Rise through the ranks."
    ),
    (
        "THE CLIMB ISN'T OVER!\n\n"
        "LEADERS OF THE LEADERBOARDS!\n\n"
        "{top1_name} currently holds #1 with {top1_points} points.\n\n"
        "{days_remaining} days remain!\n\n"
        "Race. Fly. Run.\n\n"
        "Push higher, earn points, and challenge the leaders.\n\n"
        "The top spot is within reach.\n\n"
        "🏆Will Your Name Rise To The Top🏆"
    ),
    (
        "LEADERBOARD ALERT!\n\n"
        "Who's chasing the crown?\n\n"
        "{top1_name} leads with {top1_points} points.\n"
        "{top2_name}, {top2_points}\n"
        "{top3_name}, {top3_points}\n\n"
        "Race faster. Fly higher. Run harder.\n\n"
        "Climb the rankings and challenge the leaders!\n\n"
        "Your shot at #1 is still alive.\n\n"
        "{leaderboard_url}"
    ),
    (
        "🏆 LEADERS OF THE LEADERBOARDS 🏆\n"
        "THE AEROTRAILS RACE IS LIVE! 🚀\n"
        "How high can you soar? Strap in, power up your jetpack, and choose "
        "your favorite trails. Chase the fastest times, climb every rank, "
        "and fly toward victory! ⚡\n"
        "🏁 Track your progress weekly: {leaderboard_url}"
    ),
    (
        "🚀 READY TO OWN THE SKIES?\n"
        "🏆 LEADERS OF THE LEADERBOARDS 🏆\n"
        "AeroTrails is calling! Pick your jetpack, select your trail, and "
        "push your limits. Beat the best times, rise through the rankings, "
        "and make your flight count! 🔥\n"
        "📈 Follow your climb: {leaderboard_url}"
    ),
    (
        "🔥 THE RACE TO #1 IS ON! 🔥\n\n"
        "🏆 LEADERS OF THE LEADERBOARDS 🏆\n\n"
        "🥇 {top1_name} — {top1_points} pts\n\n"
        "⏳ {days_remaining} days left!\n\n"
        "🏎️ RACE. 🚀 FLY. 🏃 RUN.\n\n"
        "Every point counts. Every position matters.\n\n"
        "⚡ CHASE THE LEAD. CLIMB THE RANKS. CLAIM #1!\n\n"
        "{leaderboard_url}"
    ),
    (
        "⚡ THE CHASE FOR #1 IS HEATING UP! ⚡\n\n"
        "🏆 LEADERBOARD SHOWDOWN 🏆\n\n"
        "🥇 {top1_name} — {top1_points} pts\n\n"
        "⏳ {days_remaining} days remain!\n\n"
        "🏎️ SPEED. 🚀 SOAR. 🏃 SPRINT.\n\n"
        "Every score matters. Every rank can shift.\n\n"
        "🔥 PUSH HIGHER. PASS THE LEADERS. TAKE THE CROWN! TODAY! 🔥\n\n"
        "{leaderboard_url}"
    ),
    (
        "🚨 THE GRID IS HOT! 🚨\n\n"
        "🏆 CALIDO PAVILION LEADERBOARD CHALLENGE 🏆\n\n"
        "Your vehicle. Your track. Your shot at glory. Push past the "
        "competition and climb toward the top!\n\n"
        "🔥 Race hard. Rise fast. Own your rank.\n\n"
        "📊 {leaderboard_url}\n\n"
        "WHO'S TAKING #1?"
    ),
    (
        "🔥 READY, SET, CLIMB! 🔥\n\n"
        "🏆 LEADERS OF THE LEADERBOARDS 🏆\n\n"
        "Calido Pavilion is calling! 🏎️💨 Pick your ride, hit your favorite "
        "trail, and chase the fastest times. Every race can move you higher!\n\n"
        "📈 Watch your ranking: {leaderboard_url}\n\n"
        "⚡ START YOUR ENGINES. CHASE #1!"
    ),
    (
        "🏆 LEADERS OF THE LEADERBOARDS 🏆\n\n"
        "🔥 HOLOCACHE LEADERBOARDS 🔥\n\n"
        "🥇 {top1_name} — {top1_points} pts\n\n"
        "How fast can YOU run?\n\n"
        "Find the Holocaches. Beat the clock. Race past the competition.\n\n"
        "Claim your place. Own the leaderboard!\n\n"
        "⏳ {days_remaining} days remaining!"
    ),
    (
        "🏆 LEADERS OF THE LEADERBOARDS 🏆\n\n"
        "🔥 HOLOCACHE RACE 🔥\n\n"
        "🥇 {top1_name} — {top1_points} pts\n\n"
        "Can YOU take the lead?\n\n"
        "🗺️ Hunt the Holocaches.\n"
        "⏱️ Beat the clock.\n"
        "🏃💨 Pass the pack.\n\n"
        "Climb higher. Run faster. Own your place!\n\n"
        "⏳ {days_remaining} days left!\n\n"
        "🔥 The leaderboard is yours to conquer! 🔥"
    ),
]

# ---------------------------------------------------------------------
# 4a. Final day boilerplate (no notable movement since last post)
#     Same placeholders as section 3, plus top1/2/3.
# ---------------------------------------------------------------------
FINAL_DAY_BOILERPLATE = [
    (
        "🏆 LEADERS OF THE LEADERBOARDS 🏆\n\n"
        "🔥 FINAL STRETCH. FULL SEND. 🔥\n\n"
        "The leaders are holding strong—but the race isn't over!\n\n"
        "📊 {leaderboard_url}\n\n"
        "⏳ {days_remaining} days remain!\n\n"
        "🥇 {top1_name} — {top1_points}\n"
        "🥈 {top2_name} — {top2_points}\n"
        "🥉 {top3_name} — {top3_points}\n\n"
        "⚡ Make your move. Chase the crown!"
    ),
    (
        "LEADERS OF THE LEADERBOARDS\n\n"
        "🔥 FINAL STRETCH! 🔥\n"
        "The leaders are holding—but the race isn't over!\n\n"
        "📊 {leaderboard_url}\n\n"
        "⏳ {days_remaining} days left!\n"
        "🥇 {top1_name} — {top1_points}\n"
        "🥈 {top2_name} — {top2_points}\n"
        "🥉 {top3_name} — {top3_points}\n\n"
        "⚡ Make your move. BE THE CHAMPION!"
    ),
    (
        "🏆 LEADERS OF THE LEADERBOARDS 🏆\n\n"
        "🔥 THE CHASE IS ON! 🔥\n\n"
        "The top spots are locked in—but who's coming for them?\n\n"
        "📊 {leaderboard_url}\n\n"
        "⏳ {days_remaining} days to shake things up!\n\n"
        "🥇 {top1_name} — {top1_points}\n"
        "🥈 {top2_name} — {top2_points}\n"
        "🥉 {top3_name} — {top3_points}\n\n"
        "⚡ Find. Run. Climb. CONQUER."
    ),
]

# ---------------------------------------------------------------------
# 4b. Final day movement callouts -- two flavors, each with rotation
#     variations. Fired only when the top-3 actually changed since the
#     last post that day.
#
#     "moved_up": someone already in top 3 changed rank, or a top-10
#                 player climbed but didn't newly enter top 3.
#                 Placeholders: name, positions_moved (+ top1/2/3 as usual)
#     "entered_top3": someone newly entered the top 3.
#                 Placeholders: name, new_rank, positions_moved (+ top1/2/3)
# ---------------------------------------------------------------------
FINAL_DAY_MOVED_UP = [
    (
        "🏆 LEADERS OF THE LEADERBOARDS 🏆\n\n"
        "THE FINAL PUSH IS ON!\n\n"
        "{name} Moved Up {positions_moved}!\n\n"
        "🏎️ Hit the tracks. 🔮 Chase Holocaches. 🚀 Fly to the top!\n\n"
        "Where do YOU stand? {leaderboard_url}\n\n"
        "🥇 {top1_name} {top1_points}\n"
        "🥈 {top2_name} {top2_points}\n"
        "🥉 {top3_name} {top3_points}\n\n"
        "MAKE YOUR MOVE!"
    ),
    (
        "🔥 LEADERS OF THE LEADERBOARDS 🔥\n\n"
        "The rankings are shifting! The final race is ON!\n\n"
        "⚡ {name} surged {positions_moved}!\n\n"
        "🏁 Race. 🔮 Hunt Holocaches. ✈️ Take flight!\n\n"
        "{leaderboard_url}\n\n"
        "🥇 {top1_name} {top1_points}\n"
        "🥈 {top2_name} {top2_points}\n"
        "🥉 {top3_name} {top3_points}\n\n"
        "WHO WILL RISE?"
    ),
    (
        "🔥 LEADERS OF THE LEADERBOARDS 🔥\n\n"
        "THE RANKINGS ARE ON FIRE! ⚡\n\n"
        "{name} jumped {positions_moved}!\n\n"
        "Push your limits. Discover Holocaches. Take your shot!\n\n"
        "{leaderboard_url}\n\n"
        "🥇 {top1_name} {top1_points}\n"
        "🥈 {top2_name} {top2_points}\n"
        "🥉 {top3_name} {top3_points}\n\n"
        "WHO TAKES THE CROWN?"
    ),
]

FINAL_DAY_ENTERED_TOP3 = [
    (
        "🔥 LEADERS OF THE LEADERBOARDS 🔥\n\n"
        "🚨 TOP 3 SHOCKWAVE! 🚨\n\n"
        "{name} just CRASHED the Top 3! 🏆 Rank #{new_rank}\n\n"
        "📈 {name} surged {positions_moved}!\n\n"
        "🏁 Race hard. 🔮 Hunt Holocaches. 🚀 Chase the climb!\n\n"
        "Where will YOU land? {leaderboard_url}\n\n"
        "⚡ THE RACE IS ON!"
    ),
    (
        "🏆 LEADERS OF THE LEADERBOARDS 🏆\n\n"
        "🚨 THE PODIUM HAS A NEW CONTENDER! 🚨\n\n"
        "{name} stormed into the Top 3! 🔥 Rank #{new_rank}\n\n"
        "⚡ {name} gained {positions_moved}!\n\n"
        "🏎️ Burn through the tracks. 🔮 Hunt Holocaches. 🚀 Climb higher!\n\n"
        "📍 {leaderboard_url}\n\n"
        "WHO'S NEXT?"
    ),
    (
        "🔥 LEADERS OF THE LEADERBOARDS 🔥\n\n"
        "🚨 THE PODIUM JUST EXPLODED! 🚨\n\n"
        "{name} BLASTED INTO THE TOP 3! 🏆 Rank #{new_rank}\n\n"
        "{name} rocketed {positions_moved}!\n\n"
        "Push harder. Hunt deeper. Climb higher!\n\n"
        "Who's making the next big move? {leaderboard_url}"
    ),
]

# ---------------------------------------------------------------------
# 5. Winners announcement -- single post, day after competition ends.
#    Placeholders: winner_name, winner_points, top2_name, top3_name
# ---------------------------------------------------------------------
WINNERS_ANNOUNCEMENT = [
    (
        "🏆 THE FINAL CROWN 🏆\n\n"
        "The Leaderboards have spoken!\n\n"
        "👑 {winner_name}, {winner_points}\n"
        "THE ULTIMATE CHAMPION!\n\n"
        "Race Track Leader\n"
        "Leader of The Skies\n"
        "Hidden Halo Leader\n\n"
        "One week. One Champion.\n\n"
        "{winner_name}\n\n"
        "CONGRATULATIONS! 🎉"
    ),
    (
        "🏆 THE MOMENT HAS ARRIVED 🏆\n\n"
        "The final scores are in. One name rises above the rest!\n\n"
        "👑 {winner_name}, {winner_points}\n\n"
        "From the track to the skies, from hidden finds to the top spot—"
        "every point mattered.\n\n"
        "👏 SALUTE OUR CHAMPION!\n\n"
        "{winner_name}\n\n"
        "THE CROWN BELONGS TO YOU!"
    ),
    (
        "🏆 THE FINAL SCORE IS IN! 🏆\n\n"
        "One name rises above the rest.\n\n"
        "👑 {winner_name}, {winner_points}\n\n"
        "From racing roads to open skies and hidden discoveries, every "
        "point brought them here.\n\n"
        "CONGRATULATIONS TO OUR RUNNERS UP'S\n\n"
        "🥈 {top2_name} 🥉 {top3_name}"
    ),
]

# ---------------------------------------------------------------------
# 6. Thank you / next competition -- single post, day after winners.
#    Placeholder: next_competition_date (computed dynamically -- see
#    poster.py -- NOT hardcoded "3rd Sunday" like the original draft,
#    since the real rule is now 2nd Sunday of the month)
# ---------------------------------------------------------------------
THANK_YOU = [
    (
        "🏆 THE CHAMPION HAS RISEN! 🏆\n\n"
        "LEADERS OF THE LEADERBOARDS has come to an end—but the battle isn't over!\n\n"
        "Thanks to everyone who competed.\n\n"
        "NEXT COMPETITION: {next_competition_date}\n\n"
        "Racing • HoloCache • AeroTrails\n\n"
        "Will YOU claim the top spot?"
    ),
    (
        "🏆 THE FINAL RANKINGS ARE SET! 🏆\n\n"
        "One Champion now stands at the top!\n\n"
        "THANK YOU to every competitor who joined the fight.\n\n"
        "But the leaderboards won't stay quiet for long...\n\n"
        "NEXT COMPETITION: {next_competition_date}\n\n"
        "Racing • HoloCache • AeroTrails\n\n"
        "Will you rise?"
    ),
]
