# Answers spread across rounds

In the NLSY97, a person's answer about a given year, or at a given age, isn't always in one obvious round. This describes how NLS's data work and what NLS documents; which approach fits an analysis is the user's choice.

**Why answers spread.**
- **Rounds change frequency.** Rounds 1–15 were annual (1997–2011), rounds 16–21 every two years (2013–2023). Fielding "began in the fall of the survey year and continued through the spring of the following year" ([Interview Methods](https://nlsinfo.org/content/cohorts/nlsy97/intro-to-the-sample/interview-methods)).
- **People miss rounds and come back.** In this slice, 44% of respondents missed at least one round and were interviewed again, and 4.8% of pairs of consecutive interviews skip a round. A round in which a person wasn't interviewed has the code -5 (non-interview) in every variable, and RNI gives the reason.
- **Many questions ask about the time "since the date of last interview" (DLI).** So the reference period is each person's own, from their previous interview to this one. After a missed round it covers the gap: NLS collects "detailed retrospective information about work history, education, training, marital status, and fertility since the date of the respondent's last interview" ([Retention & Reasons for Non-Interview](https://nlsinfo.org/content/cohorts/nlsy97/intro-to-the-sample/retention-reasons-non-interview)).
- **Wording and universes change by round.** YSAQ-360C asks "since the last interview" through 2011 and "within the past twelve months" in 2013 and 2015. "Ever" questions (YSAQ-359, YSAQ-363) were asked of everyone in 1997, and later only of those who hadn't answered as of the last interview. In each record, `questions[].waves` and the universe by wave say which.

**What NLS recommends.**
- "Researchers analyzing topics where time periods are critical should carefully examine the reference period of the questions and the actual interview date for individual respondents" ([Interview Methods](https://nlsinfo.org/content/cohorts/nlsy97/intro-to-the-sample/interview-methods)).
- For the interview date, use CV_INTERVIEW_DATE~M and ~Y (rounds 2 on) or CV_INTERVIEW_CMONTH (continuous months, January 1980 = 1). For the date of the previous interview, find the round the respondent was last interviewed, then take that round's interview date (same page).
- For status at a point in time, NLS builds **event history arrays**: employment by week, marital and cohabitation status by month, program participation, schooling, arrests and incarceration. "Using these arrays, researchers can extract the status of a respondent at a point in time or over time." They run from age 14 (12 for arrests) to the last interview ([Codebook Supplement, Appendix 6](https://nlsinfo.org/content/cohorts/nlsy97/other-documentation/codebook-supplement/appendix-6-event-history-creation-and)).
- **Created variables** (CV_ and CVC_ names) resolve common cases: the age at interview (CV_AGE_INT_DATE), "the round in which the respondent was last interviewed" (CVC_RND), and cumulative versions across rounds (CVC_, "regardless of interview status") ([Created Variable Appendices](https://nlsinfo.org/node/411); the CV_HGC_EVER_EDT codebook note).

**In this repo.**
- `person_year` has one row per respondent and survey year, so a question's answers over time are one column.
- CV_INTERVIEW_CMONTH and CV_AGE_INT_DATE give each row's interview month and age. MAR_STATUS_YYYY.MM, in `person`, is NLS's monthly marital array (group `array-mar-status`).
- To find a person's answer about year Y or at age A, the options are:
  1. the round whose interview is at that age, from CV_AGE_INT_DATE. In this slice, 14–27% of people have no interview at a given age from 16 to 25, and about half at 30 and 35;
  2. the round or rounds whose reference period covers it, for a since-the-last-interview question: from the previous interview's CV_INTERVIEW_CMONTH to this one's. For YSAQ-360C, about half of people have two or more answers whose periods overlap a given year in 2005–2010, and with twelve-month questions in a two-year cycle, 80% of people have no answer whose period overlaps 2012;
  3. NLS's event history array, for the statuses it covers. In this slice, MAR_STATUS has a value for the month a person turned 25 for 94% of respondents, against 79% with at least one interview at age 25.
- `pdt diff . 1997-2023 --waves` lists each record's changes between rounds: wording, universe, codes.
