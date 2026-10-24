# User Stories and Acceptance Criteria

Roles: **owner** (the seller) and **customer** (the buyer). Every acceptance criterion (AC) is checked by an automated test, listed under "Tests" as test classes in the `tests/` folder.

Amounts are whole rupiah. `15000`, `15.000` and `Rp 15.000` are all accepted. Dates and times use the server's local time.

---

## US-01 Register and log in
As a customer, I want my own account, so that I can order and follow my orders.
- AC1. Registration needs a full name, a username (3-30 characters: a-z, 0-9, underscore; saved in lower case) and a password of at least 8 characters. Phone is optional and must be 8-15 digits when given.
- AC2. A username that is already taken is refused, and the form keeps what the user typed.
- AC3. Public registration only creates customer accounts. Sending `role=owner` in the form has no effect.
- AC4. Passwords are stored hashed, never as plain text.
- AC5. A wrong password, an unknown user and empty fields all give the same message, "Invalid username or password.", with status 401.
- AC6. Logging out ends the session. A POST without a valid CSRF token is rejected with status 400.

Tests: `RegisterTests`, `LoginTests`, `CsrfAndErrorPageTests`, `AuthServiceTests`, `UserRepoTests`

## US-02 Role-based access
As the owner, I want customers to be kept out of my pages, so that nobody else can change my POs, menu or payments.
- AC1. A visitor who is not logged in is redirected to `/login` on every page.
- AC2. A customer who opens any `/admin` page, by GET or POST, gets HTTP 403, and no data changes.
- AC3. An owner who opens a customer ordering page gets HTTP 403.
- AC4. After login the owner lands on `/admin` and a customer on `/po`.
- AC5. A customer can only open their own orders. Someone else's order gives a 404, as if it did not exist.

Tests: `AccessControlTests`, `RoleTests`, `LoginTests`, `PayingTests`

## US-03 Manage menu items
As the owner, I want to add and edit menu items, so that customers can see what I sell.
- AC1. An item has a name (up to 60 characters), a price from Rp 1 to Rp 10.000.000 and an optional description.
- AC2. Item names are unique, ignoring upper and lower case.
- AC3. Unticking "Available" hides an item from customers without deleting it.
- AC4. Each order keeps a copy of the item name and price from the moment it was placed, so changing a price later does not change old orders.
- AC5. Bad names and prices ("abc", "0", "15.5") are refused with a message and the form keeps its values.

Tests: `MenuServiceTests`, `MenuPageTests`, `MenuRepoTests`, `QuotaTests` (price copy), `TextFieldTests`

## US-04 Create and edit a PO session
As the owner, I want to open a PO with a quota and a deadline, so that I only take as many orders as I can make.
- AC1. A PO has a name, a quota of 1 to 5000 total portions, a deadline and optional payment info that customers see after ordering.
- AC2. The deadline must be in the future and at most 180 days away.
- AC3. A new PO has status `OPEN`.
- AC4. When the input is wrong, the page shows the message, keeps the typed values and saves nothing.
- AC5. When editing, the quota can not be set lower than the portions already ordered.
- AC6. A PO whose deadline has passed can still be renamed without choosing a new deadline.

Tests: `CreateAndEditTests`, `PoSessionPageTests`, `DeadlineTests`, `PoRepoTests`

## US-05 Open and close a PO
As the owner, I want to close a PO by hand, and I want it to close by itself at the deadline, so that no order slips in late.
- AC1. The owner can close a PO at any time. A closed PO does not take orders.
- AC2. The owner can reopen a PO only if its deadline is still in the future.
- AC3. A PO whose deadline has passed is saved as `CLOSED` the next time it is listed or opened.
- AC4. A status other than `OPEN` or `CLOSED` is refused.

Tests: `StatusAndDeadlineTests`, `PoSessionPageTests`, `PoRepoTests`

## US-06 Browse open POs
As a customer, I want to see which POs are open and how many portions are left, so that I know if I can still order.
- AC1. The list shows `OPEN` POs only, each with its deadline and remaining portions.
- AC2. A PO page lists the available menu items with price and description, and hides items the owner turned off.
- AC3. A closed PO page shows a notice and no order form. A PO with no portions left shows a notice too.
- AC4. An unknown PO gives a 404.

Tests: `BrowsingTests`

## US-07 Place an order and validate the quota
As a customer, I want to choose items and quantities and send an order, so that my portions are reserved.
- AC1. A quantity is a whole number from 0 to 50 for each item, blank means 0, and at least one item is needed. A note is optional, up to 200 characters.
- AC2. A new order has status `PENDING_PAYMENT` and takes its portions from the quota at once.
- AC3. If the portions in the order are more than the portions left, the order is refused with a `ValidationError` that says how many are left, for example "Only 2 portion(s) left in this PO, but your order has 3." Nothing is saved.
- AC4. An order for exactly the portions left is accepted. The quota is shared by all menu items and all customers.
- AC5. Bad quantities ("abc", "-1", "51", empty) and items that are hidden or unknown are refused.

Tests: `QuotaTests`, `PlacingOrderTests`, `PriceQuotaAndQuantityTests`

## US-08 Deadline lock
As the owner, I want orders to stop at the deadline, so that my production list does not change after I start shopping.
- AC1. An order one minute before the deadline is accepted.
- AC2. An order at the deadline, or after it, is blocked with a message, and the PO is saved as `CLOSED`.
- AC3. The closed status stays saved after the error. It is not rolled back with the failed order.
- AC4. A PO the owner closed by hand also refuses orders, with a "closed" message.

Tests: `DeadlineLockTests`, `PlacingOrderTests`

## US-09 See the bill and confirm payment
As a customer, I want to see what I owe and tell the seller that I paid, so that the seller knows to check.
- AC1. The order page shows each line with its price, the total, and the status.
- AC2. While the order waits for payment, the page shows the owner's payment info and three options: bank transfer, e-wallet and QRIS.
- AC3. "I have paid" saves the method and the time. The status stays `PENDING_PAYMENT`, because only the owner can mark an order as paid.
- AC4. A payment can be confirmed once. A method is required. A cancelled order can not be confirmed. Another customer's order can not be confirmed.
- AC5. "My orders" lists the customer's own orders only.

Tests: `PayingTests`, `StatusTransitionTests`, `OrderQueryTests`

## US-10 Verify a payment
As the owner, I want to mark an order as paid after I checked the money, so that my revenue numbers are real.
- AC1. The PO page shows, for every waiting order, whether the customer says they paid, with the method and time.
- AC2. "Verify payment" changes `PENDING_PAYMENT` to `PAID` and saves who did it and when.
- AC3. Verifying works without a customer confirmation, for example for cash at pickup.
- AC4. A `PAID` order or a `CANCELLED` order can not be verified.

Tests: `StatusTransitionTests`, `RecapAndOrderActionTests`

## US-11 Void an order and refund the quota
As the owner, I want to cancel an order and get its portions back, so that someone else can order them.
- AC1. "Void order" works on `PENDING_PAYMENT` and `PAID` orders and changes them to `CANCELLED`. It saves who did it and when.
- AC2. The portions go back to the quota at once. A new order for those portions is accepted.
- AC3. Voiding the same order twice is refused, and the portions are not refunded twice.
- AC4. Cancelled orders are not counted in portions or revenue.

Tests: `QuotaRefundTests`, `RecapAndOrderActionTests`, `PoRepoTests`, `RecapTests`

## US-12 Recap dashboard
As the owner, I want one page that adds everything up, so that I know what to buy and cook.
- AC1. A table shows the portions and the amount per menu item, without cancelled orders.
- AC2. The page shows total portions ordered, revenue paid (verified) and the amount still waiting for verification.
- AC3. The page shows how many orders are paid, waiting and cancelled.
- AC4. Each order is listed with the customer's name and phone, the lines, the note, the total and the status.
- AC5. A quota meter shows how many portions are left.

Tests: `RecapTests`, `RecapAndOrderActionTests`, `OrderRepoTests`

## US-13 Create the first owner and try the demo
As the person setting up the app, I want to create an owner login and load demo data from the command line, so that I can run it without touching the database.
- AC1. `create-owner` creates an owner who can log in. A weak password or a username that is taken is refused with a clear message.
- AC2. `seed-demo` adds the owner, two customers, five menu items (one hidden), one open PO with three orders and one closed PO.
- AC3. Running `seed-demo` on a database that already has the demo accounts fails with a clear message, not a traceback.
- AC4. No password is stored in the source code. The caller gives them on the command line.

Tests: `CommandTests`, `DemoDataTests`
