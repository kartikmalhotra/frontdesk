# Front Desk: the 60-second video and the pilot offer

## Recording the video (Loom or QuickTime, one take is fine)

Set-up before you press record:
- Run the app with `CALENDAR_BACKEND=google` pointed at a Google Calendar you can show on screen,
  or keep the fake calendar and show `/admin` instead. Google Calendar on screen is far more
  convincing; it's worth the 15 minutes of setup.
- Set your Mac clock display to show the time. Record at night, so the clock says 10 pm or later.
- Two windows side by side: the demo site (http://localhost:8000) on the left, Google Calendar
  (week view, the clinic's calendar) on the right.
- Turn off notifications.

Script. Speak it plainly; don't read it.

**0:00–0:12. The problem.**
Screen: the demo site, clock visible.
"It's ten past ten at night. A patient has just found this clinic on Google. The clinic is closed,
nobody answers the phone, and the contact form will be read tomorrow, if at all. Most of these
people book somewhere else before morning."

**0:12–0:42. The agent.**
Screen: click the chat bubble. Type, don't paste, so it feels real.
- Type: "do you have anything tomorrow evening for a cleaning?"
  (The agent checks the calendar and offers real times.)
- Type: "6:30 works. Asha Verma, 98765 43210"
  (The agent confirms the booking.)
Say over it: "This is the clinic's booking page; the same chat goes on their website if they have one.
The receptionist answers from the clinic's real hours and prices, checks the real calendar, takes a
name and number, and books the slot. It never invents a time and it never gives medical advice;
anything it can't do, it hands to a human."

**0:42–0:58. The result.**
Screen: switch to Google Calendar. The new event is there. Click it to show the name, phone and service.
"And it's in the clinic's calendar, with the patient's details, before the clinic opens.
Every conversation is saved, so even people who don't book become leads the front desk can call back."

**0:58–1:00.**
"If you run a clinic or a salon and want this on your website, the link is below."

Export, upload to Loom or YouTube (unlisted), and put the link:
1. In the LinkedIn Featured section.
2. On aivetech.in under Work, with two lines of text.
3. In every pilot message below.

## The pilot offer

Price it so it's an easy yes and so you can learn fast, not so it pays yet.

- **Setup: ₹15,000 one-off.** You load their hours, services and prices, connect their Google
  Calendar, give them the booking page on a subdomain and put the widget on their site if they
  have one. Half a day of work.
- **Then ₹4,000 a month**, first month free. Covers hosting and the model usage, which for a small
  clinic is a few hundred rupees a month.
- In return: a review, permission to use their name as a case study, and a 20-minute call after
  four weeks about what worked.
- Cancel any time. Their data stays theirs; you export and delete on request.

Ten pilots at this price is ₹1.5 lakh up front and ₹40,000 a month recurring, plus ten case
studies. The recurring number is what matters: it's the start of the product.

## Who to pitch first

Businesses that take appointments and lose evening enquiries: dental clinics, physio and skin
clinics, salons and spas, veterinary clinics, tutoring centres, driving schools, car services.
Start with Dehradun and Delhi, where you can visit. Niladri and the Masaj contact are both
adjacent; ask them who they know.

Most Dehradun clinics have no website at all: they live on Google Maps, Practo/Justdial and
Instagram. That is the pitch, not a problem. Front Desk gives them a booking page (the page
you see at `/`, generated from their `business.yaml`) plus the chat. They put that link in
three places and every after-hours enquiry lands on it:
1. Google Business Profile → the **Appointment link** (shows as "Book online" on Maps).
2. Instagram bio.
3. WhatsApp Business → Away message: "We're closed; book here: [link]".
If they do have a website, the widget goes on it with one script tag as well.

Hosting for a pilot: one process per clinic (`BUSINESS_FILE=clinics/<name>.yaml`,
`DATABASE_PATH=clinics/<name>.db`) on a Railway/Render instance or one small VPS running the
`Dockerfile`, each on its own subdomain. A few hundred rupees a month per clinic.

## The WhatsApp message (first contact)

> Hi [Name], I'm Kartik, an engineer in Dehradun. I've built an online receptionist for clinics:
> a booking page with a chat that answers questions from your own prices and hours and books
> appointments straight into your calendar, including at night when nobody can pick up the phone.
> Here's a 60-second video of it booking an appointment: [link]. I'm setting it up for ten
> clinics in Dehradun this month at a pilot price. Would it be worth 15 minutes to see if it
> fits [Clinic name]?

Follow up once after three days, with one line: "Did you get a chance to watch it? I can show
it live with your own prices and timings in 15 minutes, at the clinic or on a call."

## The in-person pitch (if you can visit)

Walk in off-peak with your laptop. Ask the receptionist how many missed calls they get after
hours. Show the video. Offer to put it on their site this week. Clinics buy from people who turn up.
