# Design
## Source of truth
Active · 2026-11-07 · `/coding` only. Evidence: static/coding.html, coding.css, coding.js, tests/test_coding_practice.py and request for reduced-distraction study. Other application screens retain their own layouts. External evidence: [W3C focus guidance](https://www.w3.org/WAI/WCAG2/supplemental/objectives/o5-user-focus/), [task expectations](https://www.w3.org/WAI/WCAG2/supplemental/patterns/o5p04-task-expectations/), [adjustable timing](https://www.w3.org/WAI/WCAG22/Understanding/timing-adjustable.html).
## Brand
Calm, practical, respectful. Trust through saved drafts and clear next actions. Avoid clinical efficacy claims, streak pressure, flashing rewards and punitive timeouts.
## Product goals
Reduce the effort of starting and returning to Java practice. Show one problem and one immediate step. Preserve all 30 problems, Java downloads, records and backups.
## Personas and jobs
A developer preparing for an observed coding interview in two days. Needs small actionable steps, fewer distractions and easy interruption recovery. Preferences vary; controls remain optional.
## Information architecture
Default view is a narrated, code-rendered slide lesson. Each of 30 problems has five scenes with worked-example cards, a highlighted current state, a Java snippet, and Korean prerecorded audio. User starts sound explicitly; ending narration advances only when automatic progression is enabled. Practice remains accessible as a separate mode with compact current task, 3-step navigation, active work panel. Expandable full curriculum contains counts and filters. Read → implement → explain/test; steps are freely navigable. Break screen pauses work and offers explicit resume.
## Design principles
Progressive disclosure, one prominent next action, persistent context, no automatic step changes. Short sessions are adjustable design defaults, not prescribed clinical intervals.
## Visual language
Reuse green/cream palette; one-column reading width, 16px body, 1.7 line height, generous spacing. No unsolicited sounds or animated celebration. Korean narration is explicitly requested through playback controls; pause/repeat/rate and a full scene transcript are provided. Visible keyboard focus.
## Components
DOM lesson stage, actual MP3 audio, previous/next/repeat/play controls, playback speed and optional automatic next scene. Focus toolbar, native details curriculum drawer, step buttons with aria-current, 5/10/15 minute focus selector, hideable timer, break/resume panel, next-action note. Existing editor and help remain.
## Accessibility
Target WCAG 2.2 AA. Native buttons and labels; keyboard controls; no second-by-second live announcements. Reduced motion respected. Hidden panels cannot receive keyboard focus. No forced countdown, auto-submit or lost work at expiry.
## Responsive behavior
Single column by default; 390px mobile without horizontal overflow. Buttons wrap, code scrolls internally, touch targets at least 44px.
## Interaction states
Loading states disable new controls. Errors keep saved work. Timer is opt-in, pauses on break and problem changes, survives reload. Break persists on reload and does not automatically resume. Completion remains self-assessed; assisted work stays in review. Lesson progress never marks a problem independently solved. Switching problem/mode or hiding the browser pauses narration. Audio failure displays an explicit error and never silently advances. Returning restores scene position without autoplay.
## Content voice
Short Korean instructions. Say '여기서 이어가면 됩니다', not failure or guilt. Distinguish session timer from problem recommendation duration. Avoid diagnostic labels on screen.
## Implementation constraints
Vanilla JS/CSS, no dependencies, no SQLite mutations. Preserve Java storage key and Python archive. New optional state fields validate and default for old backups. Browser tests cover steps, timer, break, restoration, existing Java downloads, real audio playback and slide/audio synchronization. Narration build uses local macOS say (Yuna) and FFmpeg; playback works from committed MP3 assets without those tools. No MP4 video is generated.
## Open questions
- [ ] Preferred work interval and timer visibility — user; adjustable controls avoid blocking implementation.
