/**
 * GENERATED FILE — do not edit by hand.
 *
 * Produced from the backend's OpenAPI document by `npm run gen:types`, which
 * `npm run build` runs before tsc. To change a type here, change the Pydantic
 * model in backend/app/schemas.py and rebuild: this file is the transcription
 * that used to be done by hand, and drifted.
 */

export interface paths {
    "/api/accumulation-plans": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Accumulation Plans
         * @description List all accumulation plans.
         */
        get: operations["list_accumulation_plans_api_accumulation_plans_get"];
        put?: never;
        /**
         * Create Accumulation Plan
         * @description Create a new accumulation plan (404 if a linked institution doesn't exist).
         *
         *     `AccumulationPlanWrite` rather than `AccumulationPlanCreate`: a plan posted
         *     here must say where the money comes from and where each position will be
         *     held. Money moves from an account into a holding, and a plan that names
         *     neither end is describing a purchase nobody made — see the schema for the
         *     total it moved when it did.
         */
        post: operations["create_accumulation_plan_api_accumulation_plans_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/accumulation-plans/{plan_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Accumulation Plan
         * @description Return a single accumulation plan, or 404 if it does not exist.
         */
        get: operations["get_accumulation_plan_api_accumulation_plans__plan_id__get"];
        /**
         * Update Accumulation Plan
         * @description Update an accumulation plan (404 if it or a linked institution doesn't exist).
         *
         *     The same requirement as the POST, and this is the door a plan saved without
         *     either end is repaired through: naming them is a two-field edit. The GET
         *     keeps returning such a plan unchanged, so it can be read before it is
         *     fixed. The institutions are checked first, then the plan, as before.
         */
        put: operations["update_accumulation_plan_api_accumulation_plans__plan_id__put"];
        post?: never;
        /**
         * Delete Accumulation Plan
         * @description Delete an accumulation plan.
         */
        delete: operations["delete_accumulation_plan_api_accumulation_plans__plan_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/advisor/chain": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Chain Runs
         * @description Every analysis run, newest first: when, how deep, and whether it argued.
         *
         *     The summary is computed here rather than stored, and that is what makes it
         *     true of runs that finished before anyone thought to ask the question. The
         *     marker was already in the confidant's own text; nothing was migrated and
         *     nothing had to be.
         */
        get: operations["list_chain_runs_api_advisor_chain_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/advisor/chain/{run_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Chain Run
         * @description One analysis run: the verdict, and every step behind it.
         */
        get: operations["get_chain_run_api_advisor_chain__run_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/cash-anchors": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List All Cash Anchors
         * @description Every institution's cash anchors, by institution then date — in one
         *     request. A form that proposes the currency of an account on a date needs
         *     the anchor in force then for whichever account the reader picks, and
         *     asking per account would be one request for each of them.
         */
        get: operations["list_all_cash_anchors_api_cash_anchors_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/cash-anchors/{anchor_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Cash Anchor
         * @description Return a single cash anchor, or 404 if it does not exist.
         */
        get: operations["get_cash_anchor_api_cash_anchors__anchor_id__get"];
        /**
         * Update Cash Anchor
         * @description Update a cash anchor (409 if another anchor exists for that date).
         */
        put: operations["update_cash_anchor_api_cash_anchors__anchor_id__put"];
        post?: never;
        /**
         * Delete Cash Anchor
         * @description Delete a cash anchor.
         */
        delete: operations["delete_cash_anchor_api_cash_anchors__anchor_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/cash-anchors/{anchor_id}/deletion": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * What Deleting It Moves
         * @description What deleting this balance does to its account's cash, in the words the
         *     chat's card says it with: the account page's Delete asks with them.
         */
        get: operations["what_deleting_it_moves_api_cash_anchors__anchor_id__deletion_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/cash/positions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Cash Positions
         * @description Projected cash for every institution at `as_of` (default today).
         */
        get: operations["list_cash_positions_api_cash_positions_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/chat": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Send
         * @description Ask one more question, streaming the reply. No conversation id opens a
         *     new conversation; the `start` event says which.
         *
         *     Configuration problems (no key, no package) arrive as an `error` event
         *     rather than a 503: the client has one path for "this stopped, and here is
         *     why", whichever moment it stopped at. A conversation that does not exist
         *     is the one thing refused before the stream: there is nowhere to store the
         *     question.
         */
        post: operations["send_api_chat_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/chat/cards/{card_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Decide
         * @description Confirm or reject one proposed write, and stream what the model says
         *     about it.
         *
         *     On confirm the tool runs first, inside one unit of work with the record of
         *     it, so the card cannot end up reading "confirmed" over a write that rolled
         *     back. Only then does the stream start. The analyzer is the exception and
         *     keeps the guarantee that matters: its run is written before its card is
         *     settled, so the ordering can fail into a run no receipt names and never
         *     into a receipt over a run that did not happen.
         *
         *     Three refusals, all of them BEFORE the first byte, because a refusal
         *     arriving mid-stream is one the client has to fish out of an event — except
         *     for the analyzer, whose work is a minute long and therefore happens ON the
         *     stream. Its card is still checked here and cannot be decided twice; what
         *     moves is only the running, and a refusal that surfaces after it started
         *     arrives as an `error` event, because by then there is no status line left
         *     to send:
         *
         *       404  no card with that id
         *       409  it has already been confirmed or rejected — a decision is taken
         *            once, and a second confirm would write the row twice
         *       409  it is stale: what it was drawn against has moved since it was
         *            proposed, so what the card says would happen is no longer what
         *            would happen
         *
         *     Anything the model itself fails at afterwards arrives as an `error` event,
         *     the same as any other turn — by then the write has happened and the reader
         *     is owed the stream, not a status code. Which is why the stream says the
         *     decision first: `decided`, the card as stored, right after `start` (for
         *     the analyzer, once its run is stored), so a failure after it cannot leave
         *     the card looking undecided.
         */
        post: operations["decide_api_chat_cards__card_id__post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/chat/conversations": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Conversations
         * @description Every conversation, most recently spoken to first — the history list.
         */
        get: operations["list_conversations_api_chat_conversations_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/chat/conversations/{conversation_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Conversation
         * @description One conversation with every turn, oldest first, each card in the
         *     reader's words (`tools.present`), as the stream sends it.
         */
        get: operations["get_conversation_api_chat_conversations__conversation_id__get"];
        put?: never;
        post?: never;
        /**
         * Delete Conversation
         * @description Forget a conversation and every turn in it.
         */
        delete: operations["delete_conversation_api_chat_conversations__conversation_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/chat/models": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Models
         * @description The model dropdown, default first, each with what OpenRouter's public
         *     list says of it today.
         */
        get: operations["get_models_api_chat_models_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/dashboard/allocation": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Allocation
         * @description Allocation: financial by asset class, real by category.
         */
        get: operations["get_allocation_api_dashboard_allocation_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/dashboard/cashflow": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Cashflow
         * @description The income and expenses in force today as a monthly run-rate, the
         *     savings rate and the splits, and the flows left out: the ones still to
         *     start and the ones that have ended.
         */
        get: operations["get_cashflow_api_dashboard_cashflow_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/dashboard/net-worth-series": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Net Worth Series
         * @description Net worth over time (carry-forward), summing accounts and real assets.
         */
        get: operations["get_net_worth_series_api_dashboard_net_worth_series_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/dashboard/portfolio": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Portfolio
         * @description Investment positions (latest snapshot per institution). With ?live=true,
         *     fetch market prices (one batch) and update the price cache; otherwise reuse
         *     cached prices. Market value + P/L are computed vs the recorded value.
         */
        get: operations["get_portfolio_api_dashboard_portfolio_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/dashboard/portfolio/composition": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Portfolio Composition
         * @description Look-through composition of the whole portfolio: aggregated country and
         *     sector exposure plus cross-fund holding overlap. Per-symbol data comes
         *     from the 15-day cache; ?refresh=true forces a refetch from the sources
         *     (justETF / Morningstar / Yahoo). Positions no source can decompose stay
         *     whole and lower `coverage_pct` — honestly.
         */
        get: operations["get_portfolio_composition_api_dashboard_portfolio_composition_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/dashboard/summary": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Summary
         * @description Net worth (financial + real) and a few counts.
         */
        get: operations["get_summary_api_dashboard_summary_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/expenses": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List all expenses */
        get: operations["list_items_api_expenses_get"];
        put?: never;
        /** Create a new expense */
        post: operations["create_item_api_expenses_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/expenses/{item_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Return a single expense, or 404 if it does not exist */
        get: operations["get_item_api_expenses__item_id__get"];
        /** Update an expense */
        put: operations["update_item_api_expenses__item_id__put"];
        post?: never;
        /** Delete an expense */
        delete: operations["delete_item_api_expenses__item_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/fx/rates": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Fx Rates
         * @description The ECB reference rates in force today against the base (units per 1
         *     base): the latest published day, asked for at most once a day. Empty until
         *     the first successful fetch; ?refresh=true asks again. Each row names its
         *     base and its day, so a rate is never a bare number here either.
         */
        get: operations["get_fx_rates_api_fx_rates_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/goals": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Goals
         * @description List all goals.
         */
        get: operations["list_goals_api_goals_get"];
        put?: never;
        /**
         * Create Goal
         * @description Create a new goal.
         */
        post: operations["create_goal_api_goals_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/goals/{goal_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Goal
         * @description Return a single goal, or 404 if it does not exist.
         */
        get: operations["get_goal_api_goals__goal_id__get"];
        /**
         * Update Goal
         * @description Update a goal.
         */
        put: operations["update_goal_api_goals__goal_id__put"];
        post?: never;
        /**
         * Delete Goal
         * @description Delete a goal.
         */
        delete: operations["delete_goal_api_goals__goal_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/health": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Health
         * @description Healthcheck: confirms the backend is up.
         */
        get: operations["health_api_health_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/holdings/{holding_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Holding
         * @description Return a single holding, or 404 if it does not exist.
         */
        get: operations["get_holding_api_holdings__holding_id__get"];
        /**
         * Update Holding
         * @description Update a holding (value recomputed from quantity*price if not given).
         *     A cost left as it was keeps the units it paid for, so units typed below
         *     them are refused with a sentence (brief AV).
         */
        put: operations["update_holding_api_holdings__holding_id__put"];
        post?: never;
        /**
         * Delete Holding
         * @description Delete a holding.
         */
        delete: operations["delete_holding_api_holdings__holding_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/holdings/{holding_id}/paid-recovery": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Accept Paid
         * @description Write what the ledger paid onto this row, as the Portfolio proposed it
         *     (brief AW): the figures worked out again now, the page's only saying which
         *     proposal the reader saw. 409 with a sentence when nothing is proposed any
         *     more, the figures changed, or no rate can state them in the row's
         *     currency.
         */
        post: operations["accept_paid_api_holdings__holding_id__paid_recovery_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/holdings/{holding_id}/paid-recovery/decline": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Decline Paid
         * @description Decline this row's proposal: it is never proposed again, on this row or
         *     on a situation started from it later. 409 when nothing is proposed.
         */
        post: operations["decline_paid_api_holdings__holding_id__paid_recovery_decline_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/holdings/{holding_id}/refresh-price": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Refresh Holding Price
         * @description Fetch the live quote for a holding's symbol and update its unit price
         *     (recomputing value if the holding is quantity-based).
         */
        post: operations["refresh_holding_price_api_holdings__holding_id__refresh_price_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/income-sources": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List all income sources */
        get: operations["list_items_api_income_sources_get"];
        put?: never;
        /** Create a new income source */
        post: operations["create_item_api_income_sources_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/income-sources/{item_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Return a single income source, or 404 if it does not exist */
        get: operations["get_item_api_income_sources__item_id__get"];
        /** Update an income source */
        put: operations["update_item_api_income_sources__item_id__put"];
        post?: never;
        /** Delete an income source */
        delete: operations["delete_item_api_income_sources__item_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/institutions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Institutions
         * @description List all institutions.
         */
        get: operations["list_institutions_api_institutions_get"];
        put?: never;
        /**
         * Create Institution
         * @description Create a new institution.
         */
        post: operations["create_institution_api_institutions_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/institutions/{institution_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Institution
         * @description Return a single institution, or 404 if it does not exist.
         */
        get: operations["get_institution_api_institutions__institution_id__get"];
        /**
         * Update Institution
         * @description Update an institution.
         */
        put: operations["update_institution_api_institutions__institution_id__put"];
        post?: never;
        /**
         * Delete Institution
         * @description Delete an institution (cascades to its accounts, snapshots and holdings).
         */
        delete: operations["delete_institution_api_institutions__institution_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/institutions/{institution_id}/cash": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Cash Position
         * @description Projected cash for the institution at `as_of` (default today), with its
         *     breakdown (anchor, income, expenses, transfers).
         */
        get: operations["get_cash_position_api_institutions__institution_id__cash_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/institutions/{institution_id}/cash-anchors": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Cash Anchors
         * @description List an institution's cash anchors (chronological order).
         */
        get: operations["list_cash_anchors_api_institutions__institution_id__cash_anchors_get"];
        put?: never;
        /**
         * Create Cash Anchor
         * @description Create a dated cash anchor for the institution (409 if that date exists).
         */
        post: operations["create_cash_anchor_api_institutions__institution_id__cash_anchors_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/institutions/{institution_id}/snapshots": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Snapshots
         * @description List an institution's snapshots (chronological order).
         */
        get: operations["list_snapshots_api_institutions__institution_id__snapshots_get"];
        put?: never;
        /**
         * Create Snapshot
         * @description Create a dated snapshot for the institution (409 if that date exists).
         */
        post: operations["create_snapshot_api_institutions__institution_id__snapshots_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/institutions/{institution_id}/snapshots/prefilled": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Create Prefilled Snapshot
         * @description A new dated situation, starting from the positions of the previous one.
         *
         *     The newest snapshot is the authority for the whole institution, so one that
         *     omits a position deletes it — which is why updating a single number
         *     otherwise means re-declaring the entire account from memory. Here the list
         *     arrives already filled: everything with a ticker is re-priced for the new
         *     date, and `needs_attention` names the rows nothing could re-price, which
         *     are exactly the ones worth looking at.
         *
         *     409 if a snapshot already exists on that date; 404 if there is nothing to
         *     prefill from.
         */
        post: operations["create_prefilled_snapshot_api_institutions__institution_id__snapshots_prefilled_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/instruments/catalogue": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Catalogue Status
         * @description What the registry holds and when it was last downloaded.
         */
        get: operations["catalogue_status_api_instruments_catalogue_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/instruments/catalogue/ensure": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Ensure Catalogue
         * @description Asked at every page load. Starts a download in the background when the
         *     catalogue is missing or a week old and none is running, and answers at once
         *     with where things stand: nobody presses anything for the catalogue.
         */
        post: operations["ensure_catalogue_api_instruments_catalogue_ensure_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/instruments/catalogue/refresh": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Refresh Catalogue
         * @description Download now and wait for it, whatever the catalogue's age. No page calls
         *     it: it is the door for a download by hand, behind the same one-at-a-time
         *     guard as the app's own (409 while one runs). 502 if the source fails or
         *     sends something that is not a catalogue, the stored copy left exactly as it
         *     was, since a failed download must never leave the picker emptier than it
         *     found it.
         */
        post: operations["refresh_catalogue_api_instruments_catalogue_refresh_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/instruments/lookup": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Lookup Symbols
         * @description The live lane: shares, ETFs, crypto and futures — everything the fund
         *     catalogue cannot hold, and the only source of a symbol that actually
         *     prices.
         *
         *     Deliberately a SEPARATE endpoint from /search. The catalogue answers from
         *     SQLite in milliseconds; this one is a network call. Combining them would
         *     make the instant lane wait for the slow one, and would let an outage empty
         *     a list that had perfectly good local results to show.
         */
        get: operations["lookup_symbols_api_instruments_lookup_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/instruments/search": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Search Instruments
         * @description Instrument families matching `q`, local only.
         *
         *     Families, not rows: an accumulating fund and its distributing twin carry
         *     the same name and differ only in what they do with dividends, so showing
         *     one of a pair alone invites picking the wrong one without ever revealing
         *     there was a choice.
         */
        get: operations["search_instruments_api_instruments_search_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/liabilities": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Liabilities
         * @description List all liabilities.
         */
        get: operations["list_liabilities_api_liabilities_get"];
        put?: never;
        /**
         * Create Liability
         * @description Create a new liability (404 if the linked real asset does not exist).
         */
        post: operations["create_liability_api_liabilities_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/liabilities/{liability_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Liability
         * @description Return a single liability, or 404 if it does not exist.
         */
        get: operations["get_liability_api_liabilities__liability_id__get"];
        /**
         * Update Liability
         * @description Update a liability (404 if it, or the linked real asset, does not exist).
         */
        put: operations["update_liability_api_liabilities__liability_id__put"];
        post?: never;
        /**
         * Delete Liability
         * @description Delete a liability (cascades to its balances).
         */
        delete: operations["delete_liability_api_liabilities__liability_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/liabilities/{liability_id}/balances": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Balances
         * @description List a liability's balances (chronological order).
         */
        get: operations["list_balances_api_liabilities__liability_id__balances_get"];
        put?: never;
        /**
         * Create Balance
         * @description Add a dated balance to a liability (409 if one already exists for that date).
         */
        post: operations["create_balance_api_liabilities__liability_id__balances_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/liability-balances/{balance_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /**
         * Update Balance
         * @description Update a balance (409 if another balance exists for that liability+date).
         */
        put: operations["update_balance_api_liability_balances__balance_id__put"];
        post?: never;
        /**
         * Delete Balance
         * @description Delete a liability balance.
         */
        delete: operations["delete_balance_api_liability_balances__balance_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/overview/fund": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Fund Overview
         * @description Total wealth (the ledger's own figure, reused, never reimplemented),
         *     the engine's equity beside it, and the reconciliation gap between the
         *     broker statement and the engine — each honestly absent when it cannot
         *     be measured.
         */
        get: operations["get_fund_overview_api_overview_fund_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/overview/trading-account": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /**
         * Put Trading Account
         * @description Declare which ledger institution is the trading desk's account — the
         *     declaration the reconciliation measures against. The institution must
         *     exist: mapping to a row that is not there would reconcile against air.
         */
        put: operations["put_trading_account_api_overview_trading_account_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/paid-recovery": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Accept All Paid
         * @description Accept every proposal the page showed at once, in one transaction: all
         *     written, or none (409) if any is gone or has changed.
         */
        post: operations["accept_all_paid_api_paid_recovery_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/planning/required-return": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Required Return
         * @description Annual return needed to reach a dated target, plus a realism note.
         */
        post: operations["required_return_api_planning_required_return_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/prices/listing-currencies": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Listing Currencies
         * @description {symbol: currency} for every listing whose trading currency is known,
         *     from the price cache alone — no market call. What a ledger form proposes as
         *     the currency of a price, before anyone has typed one.
         */
        get: operations["get_listing_currencies_api_prices_listing_currencies_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/prices/quote": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Quote
         * @description Price for a Yahoo symbol (e.g. VWCE.MI, AAPL, BTC-EUR): the latest
         *     close, or the close on a given date when `on` is passed — which is what
         *     turns backfilling an old purchase into typing a date and a quantity.
         *
         *     A dated close comes back without a currency from the market, and the
         *     currency it is in is exactly what a ledger entry has to state. A listing's
         *     currency does not change, so the one the price cache has learned for the
         *     symbol is given with it; a symbol nothing has priced yet has none to give.
         */
        get: operations["get_quote_api_prices_quote_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/prices/resolve": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Resolve Isin
         * @description Suggest tickers for an ISIN (you may need to add a Yahoo suffix like .MI).
         */
        get: operations["resolve_isin_api_prices_resolve_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/real-asset-valuations/{valuation_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Valuation
         * @description Return a single valuation, or 404 if it does not exist.
         */
        get: operations["get_valuation_api_real_asset_valuations__valuation_id__get"];
        /**
         * Update Valuation
         * @description Update a valuation (409 if another valuation exists for that asset+date).
         */
        put: operations["update_valuation_api_real_asset_valuations__valuation_id__put"];
        post?: never;
        /**
         * Delete Valuation
         * @description Delete a real-asset valuation.
         */
        delete: operations["delete_valuation_api_real_asset_valuations__valuation_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/real-assets": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Real Assets
         * @description List all real assets.
         */
        get: operations["list_real_assets_api_real_assets_get"];
        put?: never;
        /**
         * Create Real Asset
         * @description Create a new real asset.
         */
        post: operations["create_real_asset_api_real_assets_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/real-assets/{real_asset_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Real Asset
         * @description Return a single real asset, or 404 if it does not exist.
         */
        get: operations["get_real_asset_api_real_assets__real_asset_id__get"];
        /**
         * Update Real Asset
         * @description Update a real asset.
         */
        put: operations["update_real_asset_api_real_assets__real_asset_id__put"];
        post?: never;
        /**
         * Delete Real Asset
         * @description Delete a real asset (cascades to its valuations).
         */
        delete: operations["delete_real_asset_api_real_assets__real_asset_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/real-assets/{real_asset_id}/valuations": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Valuations
         * @description List a real asset's valuations (chronological order).
         */
        get: operations["list_valuations_api_real_assets__real_asset_id__valuations_get"];
        put?: never;
        /**
         * Create Valuation
         * @description Add a dated valuation to a real asset (409 if one already exists for that date).
         */
        post: operations["create_valuation_api_real_assets__real_asset_id__valuations_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/settings/base-currency": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Base Currency
         * @description The currency every total is shown in, and the ones it can become: the
         *     currencies the ECB feed quotes, because a total can only be converted into
         *     a currency somebody publishes a rate for.
         */
        get: operations["get_base_currency_api_settings_base_currency_get"];
        /**
         * Put Base Currency
         * @description Change the base. Every total moves — the history's too — because it is
         *     the same wealth in another unit; no recorded amount is rewritten.
         *
         *     422 for a currency the feed does not quote. 503, with nothing changed, when
         *     the rates against the new base cannot be stored first: see
         *     `fx.choose_base` for why a base is not chosen before its rates are in. The
         *     rules are `crud.change_base`'s, which the chat's card goes through too.
         */
        put: operations["put_base_currency_api_settings_base_currency_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/settings/tax": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Tax Settings
         * @description The declared rates, with the handful of countries this app ships a
         *     default for. The defaults come down as data to OFFER, never applied: a
         *     reader's own figure beats any table shipped here, and a rate that changed
         *     itself because a country field changed is a rate nobody declared.
         */
        get: operations["get_tax_settings_api_settings_tax_get"];
        /**
         * Put Tax Settings
         * @description Replace all three. A null clears that key, which is how the reader says
         *     they do not know a rate — distinct from writing 0, which claims they pay
         *     nothing.
         */
        put: operations["put_tax_settings_api_settings_tax_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/snapshots/{snapshot_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Snapshot
         * @description Return a single snapshot, or 404 if it does not exist.
         */
        get: operations["get_snapshot_api_snapshots__snapshot_id__get"];
        /**
         * Update Snapshot
         * @description Update a snapshot (409 if another snapshot exists for that institution+date).
         */
        put: operations["update_snapshot_api_snapshots__snapshot_id__put"];
        post?: never;
        /**
         * Delete Snapshot
         * @description Delete a snapshot (cascades to its holdings).
         */
        delete: operations["delete_snapshot_api_snapshots__snapshot_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/snapshots/{snapshot_id}/holdings": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Holdings
         * @description List a snapshot's holdings.
         */
        get: operations["list_holdings_api_snapshots__snapshot_id__holdings_get"];
        put?: never;
        /**
         * Create Holding
         * @description Add a holding to the given snapshot.
         */
        post: operations["create_holding_api_snapshots__snapshot_id__holdings_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/survey": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Survey
         * @description Return all stored questionnaire answers.
         */
        get: operations["get_survey_api_survey_get"];
        /**
         * Put Survey
         * @description Replace the whole set of answers with the provided ones.
         */
        put: operations["put_survey_api_survey_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/survey/questions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Survey Questions
         * @description The Profile form's questions, in its order: the form draws itself from
         *     this list, and the chat's answers to them are checked against it
         *     (`app/questionnaire.py`).
         */
        get: operations["get_survey_questions_api_survey_questions_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/trading/backtest-runs": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Backtest Runs
         * @description The last 50 backtest runs, each with the verdict its validation reached.
         */
        get: operations["list_backtest_runs_api_trading_backtest_runs_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/trading/backtest-runs/{run_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Backtest Run Detail
         * @description One run with everything its verdict stands on: params, seed, data provenance.
         */
        get: operations["backtest_run_detail_api_trading_backtest_runs__run_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/trading/divergence": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Trading Divergence
         * @description The slice-5 divergence surface: per bot, the declared budget, the live
         *     feed counters, the aggregated per-fill drift evidence, and the paper-vs-
         *     backtest distributional comparison when the data volume makes it
         *     meaningful (n≥30 on BOTH sides — the validation gate's own statistical
         *     bar; smaller samples are reported as insufficient, never as fake
         *     statistics).
         *
         *     Sources, honestly separated: budgets and feed counters come from the
         *     desk runner's rail snapshots (kernel memory is the truth, the snapshot
         *     its rendering), per-fill evidence aggregates the trade rows the desk
         *     wrote at fill time. Bots present in neither surface simply do not
         *     appear — an engine that never ran has no divergence to measure, and
         *     empty is the first-class answer.
         */
        get: operations["trading_divergence_api_trading_divergence_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/trading/kill-switch": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Set Kill Switch
         * @description The manual kill-switch — write path of the row the kernel polls
         *     fail-closed at entry cadence (trading/risk.py `__killswitch` on
         *     BotStatus; the desk's manual_halt_check reads it before every entry).
         *
         *     Direction is asymmetric on purpose: throwing the switch ON is always
         *     allowed and immediate, note optional — in that direction speed beats
         *     paperwork, and halting is the safe failure. Re-arming (enabled=false)
         *     is the dangerous direction, so it demands the operator's sentence: the
         *     note is mandatory, enforced here server-side, and both directions write
         *     a risk_events audit row — the control tape and the rail tape are one
         *     tape, so a veto read next to the switch's throw explains itself without
         *     a second panel. Entries halt immediately; protective exits always keep
         *     flowing, because the switch refuses entries, never safety.
         */
        post: operations["set_kill_switch_api_trading_kill_switch_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/trading/model-registry": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Model Registry
         * @description The ML model registry: every version with its OOS evidence and its
         *     role — champion (the gate's live weights), challenger (the newest version
         *     of a name that is not the champion), retired (everything else). PSI drift
         *     is NOT a column today: the retrain cycle computes it and it travels in
         *     the supervisor insight's text — null on the wire is the documented,
         *     honest answer rather than a parsed-out-of-prose fiction.
         */
        get: operations["model_registry_api_trading_model_registry_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/trading/positions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Positions
         * @description Every open position the desk has written. Empty is the honest answer
         *     both for "no engine ever ran" and for "the engine runs flat" — the row
         *     set IS the state; the engine lamp on /status is how the two read apart.
         */
        get: operations["list_positions_api_trading_positions_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/trading/positions/recent-trades": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Recent Trades
         * @description The last 25 settled round-trips — evidence the desk actually traded,
         *     newest first. Same empty-is-honest contract as /positions.
         */
        get: operations["list_recent_trades_api_trading_positions_recent_trades_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/trading/rails": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Trading Rails
         * @description Per-bot rail state: the kill-switches, the daily loss consumed, the
         *     loss-streak cooldown, exposure against the caps, and the recent
         *     risk_events the rails wrote to explain themselves.
         *
         *     Sources, honestly separated: the manual kill-switch and the halt
         *     sentinel are read LIVE (they are external halts — a cached answer would
         *     be a lie by design), the per-bot rails come from the desk runner's
         *     snapshots (kernel memory is the truth; the snapshot is its rendering),
         *     and the events come from the risk_events table. Empty is the first-class
         *     answer: an engine that never ran has rails and no rail state.
         */
        get: operations["trading_rails_api_trading_rails_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/trading/registry": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Trading Registry
         * @description Every registered strategy version with state, evidence chain, paper
         *     track record and staleness fingerprint. Empty is the first-class answer:
         *     with zero validated strategies the lifecycle owns nothing — the gate
         *     working, not a missing panel.
         */
        get: operations["trading_registry_api_trading_registry_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/trading/registry/{version_id}/approve": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Approve Version
         * @description The paper → candidate_live approval card, exactly as design §6 layer 1
         *     demands: human, mandatory, one click, re-basing impossible.
         *
         *     The card's contract: the body carries the fingerprint GET /registry
         *     served beside the track record the human reviewed. The fingerprint is
         *     recomputed from CURRENT rows and compared — a mismatch is 409, "inputs
         *     moved — review the new track record", and nothing is written. On match
         *     the approval row is written first (the durable assent, the audit) and
         *     the registry's transition() applies its own guards; a refusal there is
         *     surfaced honestly as 409 with the guard's reason, and both writes roll
         *     back together — a half-written approval would be a forged card.
         */
        post: operations["approve_version_api_trading_registry__version_id__approve_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/trading/signals/today": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Signals Today
         * @description Today's emissions including the rejected ones (UTC day, server clock —
         *     the same wall the vetoes tape uses). The table fills only from the kernel
         *     desk's recording seam; a database whose engine predates it answers empty,
         *     and empty is honest twice over: no engine ran, or no strategy spoke.
         */
        get: operations["signals_today_api_trading_signals_today_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/trading/status": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Trading Status
         * @description Engine state at a glance; offline is an answer, not a failure.
         */
        get: operations["trading_status_api_trading_status_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/trading/strategies": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Trading Strategies
         * @description The catalog of ported strategies, with the lifecycle registry's
         *     answer beside each: registered means a strategies row exists — the
         *     explicit act — never that capital followed it (that is the roster,
         *     versions in state paper, which /rails and /status reflect).
         */
        get: operations["trading_strategies_api_trading_strategies_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/trading/strategy-panels": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Strategy Panels
         * @description Per-bot panel data for TRADING OPS: the cumulative realized net pnl
         *     curve per bot, derived from the desk's own closed trades — equity_points
         *     rows are portfolio-wide by design, so a per-bot equity figure would be an
         *     allocation fiction; realized pnl is not. Empty bots are simply absent.
         */
        get: operations["strategy_panels_api_trading_strategy_panels_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/trading/validation-queue": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Validation Queue
         * @description The RESEARCH validation queue: versions sitting in research state —
         *     registered, never promoted past the gate — beside the gate's failures
         *     with the reasons it wrote. Both empty is honest: nothing in flight,
         *     nothing failed.
         */
        get: operations["validation_queue_api_trading_validation_queue_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/transactions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Transactions
         * @description All recorded transactions, most recent first.
         */
        get: operations["list_transactions_api_transactions_get"];
        put?: never;
        /**
         * Create Transaction
         * @description Record a buy manually (a purchase made outside any PAC).
         *
         *     `TransactionWrite` rather than `TransactionCreate`: an entry posted here
         *     must name the institution holding it, because the cash has to leave a real
         *     account. The PAC writes through `crud` directly and keeps its looser
         *     payload — see the schema for what the difference is and why it is not a
         *     migration.
         */
        post: operations["create_transaction_api_transactions_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/transactions/{tx_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Transaction */
        get: operations["get_transaction_api_transactions__tx_id__get"];
        /**
         * Update Transaction
         * @description Correct a transaction with the real broker fill (clears `estimated`).
         *
         *     The same requirement as the POST, and this is the door an existing
         *     institution-less row is repaired through: attaching one is a one-field
         *     edit.
         */
        put: operations["update_transaction_api_transactions__tx_id__put"];
        post?: never;
        /**
         * Delete Transaction
         * @description Delete an entry, and the catch-up leaves it deleted: a PAC's occurrence
         *     whose last buy goes stays settled and is never bought again, the plan's
         *     carry going to zero; a dividend is not recorded again, by its ex-date
         *     wherever its row was dated. The chat's card deletes through the same
         *     function (`crud.delete_transaction`).
         */
        delete: operations["delete_transaction_api_transactions__tx_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/transactions/catch-up": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Catch Up
         * @description Ledger catch-up (idempotent — safe to call at every app start): a Buy
         *     for every elapsed, still-unexecuted PAC occurrence at that day's close,
         *     and a dividend entry for every ex-date of every position that follows its
         *     dividends: stated distributing, or stating no policy, when its own history
         *     decides. Items that cannot be priced are skipped and retried on the next
         *     run. A dividend the reader entered themselves is recognised rather than
         *     recorded beside it, and what only the reader can say is asked.
         */
        post: operations["catch_up_api_transactions_catch_up_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/transactions/dividend-answer": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Answer Dividend
         * @description The reader's answer to a question the catch-up asked about a dividend:
         *     an entry of theirs is the dividend with that ex-date, or it is not. The
         *     dividend catch-up then runs again and returns what it recorded and what it
         *     still asks. 409 with a sentence when the question no longer stands.
         */
        post: operations["answer_dividend_api_transactions_dividend_answer_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/transfers": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Transfers
         * @description List all transfers (chronological order).
         */
        get: operations["list_transfers_api_transfers_get"];
        put?: never;
        /**
         * Create Transfer
         * @description Create a cash transfer between institutions.
         */
        post: operations["create_transfer_api_transfers_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/transfers/{transfer_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Transfer
         * @description Return a single transfer, or 404 if it does not exist.
         */
        get: operations["get_transfer_api_transfers__transfer_id__get"];
        /**
         * Update Transfer
         * @description Update a transfer. A `to_amount` sent empty is worked out again, at the
         *     rate final for the (possibly new) date; one left OUT of the body is not
         *     touched at all, like every other column the request does not mention —
         *     see `crud._update`.
         */
        put: operations["update_transfer_api_transfers__transfer_id__put"];
        post?: never;
        /**
         * Delete Transfer
         * @description Delete a transfer.
         */
        delete: operations["delete_transfer_api_transfers__transfer_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/transfers/{transfer_id}/deletion": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * What Deleting It Moves
         * @description What deleting this transfer does to each account's cash, in the words
         *     the chat's card says it with: the Cash flow page's Delete asks with them.
         */
        get: operations["what_deleting_it_moves_api_transfers__transfer_id__deletion_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/watchlist": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Watchlist
         * @description Every idea on the list, most recently added first.
         */
        get: operations["list_watchlist_api_watchlist_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/watchlist/{item_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        /**
         * Delete Watchlist Item
         * @description Drop one idea. It owned nothing, so nothing is recomputed.
         */
        delete: operations["delete_watchlist_item_api_watchlist__item_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
}
export type webhooks = Record<string, never>;
export interface components {
    schemas: {
        /**
         * AccumulationPlanRead
         * @description A stored accumulation plan as returned by the API.
         */
        AccumulationPlanRead: {
            /**
             * Amount
             * @description Amount contributed per occurrence
             */
            amount: number;
            /**
             * Carried Remainder
             * @description What the last whole-unit contribution could not place, waiting for the next one. Shown because money set aside and not yet invested is a fact the saver is entitled to see, not an implementation detail.
             * @default 0
             */
            carried_remainder: number;
            /** Created At */
            created_at: string;
            /**
             * Currency
             * @description Currency the contribution is paid in: the source account's cash, e.g. EUR
             */
            currency: string;
            /**
             * End Date
             * @description Last contribution (optional)
             */
            end_date: string | null;
            /**
             * Execution
             * @description How the broker fills the order: whole_units (floor(amount/price), remainder stays in cash — default) | fractional (exactly `amount`)
             */
            execution: string | null;
            /**
             * Frequency
             * @description monthly | quarterly | semiannual | annual
             */
            frequency: string | null;
            /** Id */
            id: number;
            /**
             * Name
             * @description Plan name (e.g. 'PAC All-World')
             */
            name: string;
            /**
             * Notes
             * @description Free-form notes
             */
            notes: string | null;
            /**
             * Source Institution Id
             * @description Institution whose cash funds the plan
             */
            source_institution_id: number | null;
            /**
             * Start Date
             * @description First contribution
             */
            start_date: string | null;
            /** Targets */
            targets: components["schemas"]["PlanTargetRead"][];
        };
        /**
         * AccumulationPlanWrite
         * @description What a PERSON may post to `/api/accumulation-plans` — which is not the
         *     same thing as what the tables are able to store.
         *
         *     Both ends of the sentence are required here, and both are optional
         *     everywhere else. Money moves FROM an account INTO a holding, and a plan
         *     that names neither end describes a purchase nobody made:
         *
         *     - No SOURCE and no target institution is the defect `TransactionWrite`
         *       already closed on the ledger, reached through a second door. `pac.py`
         *       writes `cash_institution_id=plan.source_institution_id`, so with no
         *       source both institution columns of every buy it creates are null — and
         *       the cash register keeps only the entries belonging to the institution it
         *       is computing, where null equals no id there is. The cash side is skipped
         *       everywhere, the position side counts in full, and the plan's spending
         *       adds itself to the net worth. Measured on a scratch database: 1000.00 of
         *       cash, two elapsed occurrences of 100.00 each, net worth 1000.00 ->
         *       1200.00 with the cash untouched at 1000.00.
         *
         *     - No TARGET institution alone does not move a total: the source names the
         *       cash side and the arithmetic stays right to the cent. It creates a
         *       position held at no institution, which no situation can photograph, no
         *       snapshot can reconcile, and — since a `close` is matched to its position
         *       by institution — no disposal can settle. `ca4858d` called requiring this
         *       a separate decision; this is that decision.
         *
         *     The columns stay nullable and `AccumulationPlanCreate` stays loose on
         *     purpose. `crud` is the internal door, nothing migrates, and a plan already
         *     saved without either end stays readable through the GET rather than
         *     becoming a row the app refuses to show. What it cannot do is run: see
         *     `pac.execute_due`, which skips a source-less plan with the reason instead
         *     of spending money it cannot take from anywhere.
         */
        AccumulationPlanWrite: {
            /**
             * Amount
             * @description Amount contributed per occurrence
             */
            amount: number;
            /**
             * Currency
             * @description Currency the contribution is paid in: the source account's cash, e.g. EUR
             */
            currency: string;
            /**
             * End Date
             * @description Last contribution (optional)
             */
            end_date?: string | null;
            /**
             * Execution
             * @description How the broker fills the order: whole_units (floor(amount/price), remainder stays in cash — default) | fractional (exactly `amount`)
             */
            execution?: string | null;
            /**
             * Frequency
             * @description monthly | quarterly | semiannual | annual
             */
            frequency?: string | null;
            /**
             * Name
             * @description Plan name (e.g. 'PAC All-World')
             */
            name: string;
            /**
             * Notes
             * @description Free-form notes
             */
            notes?: string | null;
            /**
             * Source Institution Id
             * @description The account whose cash funds the plan. Required: a plan that does not say where the money comes from cannot take it from anywhere, and every buy it writes spends money no account loses.
             */
            source_institution_id: number;
            /**
             * Start Date
             * @description First contribution
             */
            start_date?: string | null;
            /**
             * Targets
             * @description Instruments this plan buys, with their weights
             */
            targets?: components["schemas"]["PlanTargetWrite"][];
        };
        /**
         * AllocationSlice
         * @description One country/sector with its weight (percent, 0-100).
         */
        AllocationSlice: {
            /** Name */
            name: string;
            /** Pct */
            pct: number;
        };
        /**
         * ApproveRequest
         * @description POST /api/trading/registry/<id>/approve body. `fingerprint` is the
         *     exact digest GET /api/trading/registry served with the track record the
         *     human reviewed — the card's staleness check. If ANY input moved since
         *     (a trade settled, drift counters ticked, a validation landed) the digest
         *     no longer matches and the write is refused 409: re-basing is impossible,
         *     the human reviews the NEW track record. `note` is the operator's sentence
         *     on the approval row itself.
         */
        ApproveRequest: {
            /** Fingerprint */
            fingerprint: string;
            /**
             * Note
             * @default
             */
            note?: string;
        };
        /**
         * ArrivedPosition
         * @description A row a situation declared that the app was not expecting.
         *
         *     Only reported for a situation that ALSO failed to account for something,
         *     because value arriving breaks no rule on its own — a reader may declare
         *     whatever they hold. Beside what went missing it is usually the same money
         *     described better, and the two numbers together are what tell a
         *     reformulation from a loss.
         */
        ArrivedPosition: {
            /** Appeared On */
            appeared_on: string;
            /** Asset Name */
            asset_name: string;
            /** Institution */
            institution: string | null;
            /** Institution Id */
            institution_id: number | null;
            /** Symbol */
            symbol: string | null;
            /** Value */
            value: number;
        };
        /**
         * AssetClassSlice
         * @description One slice of the financial allocation (by asset class).
         */
        AssetClassSlice: {
            /** Asset Class */
            asset_class: string;
            /** Value */
            value: number;
        };
        /**
         * BaseCurrencySetting
         * @description The currency every total is shown in.
         */
        BaseCurrencySetting: {
            /**
             * Base Currency
             * @description An ISO code the ECB reference-rate feed quotes, e.g. EUR, USD
             */
            base_currency: string;
        };
        /**
         * BaseCurrencySettingRead
         * @description The base, and the currencies it may be changed to.
         */
        BaseCurrencySettingRead: {
            /**
             * Available
             * @description The currencies the ECB feed quotes today, which are the only ones a total can be converted into. Just the current base when the feed has never been reached.
             */
            available: string[];
            /**
             * Base Currency
             * @description An ISO code the ECB reference-rate feed quotes, e.g. EUR, USD
             */
            base_currency: string;
        };
        /**
         * CashAnchorCreate
         * @description Payload to create an anchor. institution_id comes from the URL.
         */
        CashAnchorCreate: {
            /**
             * Amount
             * @description Actual cash at that date
             */
            amount: number;
            /**
             * Currency
             * @description Currency, e.g. EUR
             */
            currency: string;
            /**
             * Date
             * Format: date
             * @description Balance date (YYYY-MM-DD)
             */
            date: string;
            /**
             * Note
             * @description Free-form notes
             */
            note?: string | null;
        };
        /**
         * CashAnchorRead
         * @description A stored anchor as returned by the API.
         */
        CashAnchorRead: {
            /**
             * Amount
             * @description Actual cash at that date
             */
            amount: number;
            /** Created At */
            created_at: string;
            /**
             * Currency
             * @description Currency, e.g. EUR
             */
            currency: string;
            /**
             * Date
             * Format: date
             * @description Balance date (YYYY-MM-DD)
             */
            date: string;
            /** Id */
            id: number;
            /** Institution Id */
            institution_id: number;
            /**
             * Note
             * @description Free-form notes
             */
            note: string | null;
        };
        /**
         * CashFlowSummary
         * @description The income and expenses IN FORCE today as a monthly run-rate, one-offs
         *     excluded, and the flows those figures leave out
         *     (`analytics.compute_flows_in_force`, the analysis's own computation).
         */
        CashFlowSummary: {
            /** Active Income */
            active_income: number;
            /**
             * Base Currency
             * @description The currency this payload's computed amounts are in — the database's base, as the figures were converted. Figures a row states itself (an anchor, a transaction, a valuation) keep their own `currency`.
             */
            base_currency: string;
            /** Discretionary Expenses */
            discretionary_expenses: number;
            /**
             * Ended
             * @description Ended before today: no longer counted
             */
            ended: components["schemas"]["FlowNotCounted"][];
            /** Essential Expenses */
            essential_expenses: number;
            /** Expenses In Force */
            expenses_in_force: number;
            /**
             * Incomes In Force
             * @description So 'none in force' can be told from a sum of zero
             */
            incomes_in_force: number;
            /** Monthly Expenses */
            monthly_expenses: number;
            /** Monthly Income */
            monthly_income: number;
            /** Monthly Net */
            monthly_net: number;
            /**
             * On
             * Format: date
             * @description The day the flows are in force on: today
             */
            on: string;
            /** Passive Income */
            passive_income: number;
            /** Savings Rate */
            savings_rate: number | null;
            /**
             * Scheduled
             * @description First payment after today: not counted until then
             */
            scheduled: components["schemas"]["FlowNotCounted"][];
            /**
             * Unconverted
             * @description The codes these monthly figures hold as written, because no rate converts them, with a month's share of each (brief BA).
             */
            unconverted: components["schemas"]["UnconvertedCode"][];
            /**
             * Undated
             * @description Flows with no start date, counted as in force: nothing says they have not started
             */
            undated: number;
        };
        /**
         * CashPosition
         * @description Projected cash for one institution at `as_of`, with its breakdown:
         *     projected = anchor_amount + income − expenses + transfers_in − transfers_out
         *     − buys (events counted only AFTER the anchor date, up to as_of).
         */
        CashPosition: {
            /** Anchor Amount */
            anchor_amount: number;
            /** Anchor Date */
            anchor_date: string | null;
            /**
             * As Of
             * Format: date
             */
            as_of: string;
            /**
             * Base Currency
             * @description The currency this payload's computed amounts are in — the database's base, as the figures were converted. Figures a row states itself (an anchor, a transaction, a valuation) keep their own `currency`.
             */
            base_currency: string;
            /**
             * Buys
             * @description Investment purchases paid by this institution's cash
             */
            buys: number;
            /** Expenses */
            expenses: number;
            /** Income */
            income: number;
            /** Institution Id */
            institution_id: number;
            /** Institution Name */
            institution_name: string;
            /** Projected */
            projected: number;
            /**
             * Sells
             * @description Sale proceeds and dividends credited to this institution
             */
            sells: number;
            /** Transfers In */
            transfers_in: number;
            /** Transfers Out */
            transfers_out: number;
            /**
             * Unconverted
             * @description The codes this account's cash holds as written, because no rate converts them, with their share of it under "projected" (brief BA).
             */
            unconverted: components["schemas"]["UnconvertedCode"][];
        };
        /**
         * CatalogueStatus
         * @description What the local registry holds and how old it is. Shown, not assumed: a
         *     picker searching a catalogue downloaded months ago is a different tool from
         *     one searching today's.
         *
         *     `state` is where the app's own download stands: "downloading"; "failed",
         *     tried again at a page load from `retry_after` on; "ready"; or
         *     "not_started", an empty registry nobody has asked about since the server
         *     started (a reload asks).
         */
        CatalogueStatus: {
            /** Fetched At */
            fetched_at: string | null;
            /** Retry After */
            retry_after: string | null;
            /**
             * Rows
             * @default 0
             */
            rows: number;
            /** Source */
            source: string | null;
            /**
             * State
             * @default ready
             * @enum {string}
             */
            state: "ready" | "downloading" | "failed" | "not_started";
        };
        /**
         * CatchUpResult
         * @description Outcome of a catch-up run: transactions created for every elapsed,
         *     still-unrecorded PAC occurrence and dividend ex-date, plus what was
         *     skipped (retried on the next run), the dividends the reader had entered
         *     themselves and the questions only they can answer (brief AZ).
         */
        CatchUpResult: {
            /**
             * Accounts
             * @description The name of every account a created entry belongs to, by its id: what the banner lists the recorded dividends under.
             */
            accounts: {
                [key: string]: string;
            };
            /** Created */
            created: components["schemas"]["TransactionRead"][];
            /** Questions */
            questions: components["schemas"]["DividendQuestion"][];
            /** Recognised */
            recognised: components["schemas"]["DividendRecognised"][];
            /** Skipped */
            skipped: components["schemas"]["CatchUpSkip"][];
            /** Waiting */
            waiting: components["schemas"]["DividendWaiting"][];
        };
        /**
         * CatchUpSkip
         * @description One catch-up item that could NOT be executed, and why. `label` names
         *     the source (a PAC plan or a dividend-paying symbol).
         */
        CatchUpSkip: {
            /** Label */
            label: string;
            /** Occurrence */
            occurrence: string | null;
            /** Reason */
            reason: string;
        };
        /**
         * ChainRunRead
         * @description A chain run: the final verdict plus every step, so the reasoning stays
         *     inspectable.
         */
        ChainRunRead: {
            /** Created At */
            created_at: string;
            /** Id */
            id: number;
            /** Steps */
            steps: components["schemas"]["ChainStepRead"][];
            /** Verdict */
            verdict: string | null;
        };
        /**
         * ChainRunSummary
         * @description One run as a LIST reads it: when it ran, how deep it went, and whether
         *     the confidant actually argued.
         *
         *     No text. The verdict is a document and the steps are four more of them, and
         *     a list that carried them would download every word four models ever wrote
         *     so the reader could choose a date.
         *
         *     `challenge` is the whole point of the shape. The chain's value is that the
         *     confidant is adversarial, and a mandate that never bites is an expensive
         *     way to agree with yourself — so whether it bit has to be readable from
         *     outside the run, and across runs it is a count. It is the confidant's own
         *     `VERDICT:` marker and not an inference from how many steps there were: the
         *     two can disagree, and the marker is the one that says what was meant.
         *
         *     'unstated' is a third answer and not a quiet 'fits'. It means no turn of
         *     that run ended on a marker this code recognises, so the run says nothing
         *     about the mandate either way and must not be counted as if it did.
         */
        ChainRunSummary: {
            /**
             * Challenge
             * @description The confidant's own VERDICT marker for the run: whether it challenged something that mattered, waved the findings through, or ended on no marker at all
             * @enum {string}
             */
            challenge: "contested" | "fits" | "unstated";
            /** Created At */
            created_at: string;
            /** Id */
            id: number;
            /**
             * Revisions
             * @description How many times the analyst was asked to answer the challenge — the depth the argument actually bought
             */
            revisions: number;
            /**
             * Step Count
             * @description How many turns the run took, 3 to 7
             */
            step_count: number;
        };
        /**
         * ChainStepRead
         * @description One role's turn in a chain run, with the model that produced it.
         */
        ChainStepRead: {
            /** Cost */
            cost: number | null;
            /** Duration Ms */
            duration_ms: number | null;
            /** Model */
            model: string | null;
            /** Output */
            output: string;
            /** Role */
            role: string;
            /** Step No */
            step_no: number;
            /** Title */
            title: string;
        };
        /**
         * ChatCard
         * @description A card has been proposed, and the turn is about to end on it.
         *
         *     It carries the block itself rather than repeating its fields, so the panel
         *     renders one shape whether the card just arrived or was read back from the
         *     history — and so the two cannot come to disagree, which nine fields
         *     written out twice eventually do.
         *
         *     The turn ENDS here, and ends on `done`. SSE is one-directional and the
         *     confirmation is a new request, so holding the stream open while a person
         *     decides would leave a call billing to nobody — and would need a fourth
         *     ending called "waiting for you", which `cut` would then be indistinguishable
         *     from. A closed browser leaves nothing pending: the card is a stored block,
         *     so it is still there when the reader comes back, and so is the fact that
         *     they never answered it.
         */
        ChatCard: {
            card: components["schemas"]["ChatCardBlock"];
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "card";
        };
        /**
         * ChatCardBlock
         * @description A write the model PROPOSED, and what became of it.
         *
         *     Nothing has happened when this is written. The model never calls `crud`;
         *     it drafts a change, this is how the change is shown, and the write runs
         *     from the normal path only after the reader confirms it — same `crud`, same
         *     unit of work, same contract the form goes through. The chat does not get a
         *     service door the form does not have, and a wrong field is corrected on the
         *     card rather than in the database.
         *
         *     `outcome` and `result` are why the block is rewritten in place instead of
         *     a second block being appended: a history that shows what was proposed and
         *     not what happened is a "done!" with no receipt, and a rejected card has to
         *     stay visible as a rejected card. Both states are on record.
         *
         *     `card_id` exists because a block otherwise has no address — the JSON list
         *     has no key and its index is not promised to be stable — and the endpoint
         *     that settles this one has to be able to name it.
         *
         *     `call_id` is the id the MODEL's tool call carried, kept so the exchange can
         *     be replayed to it: the API pairs an assistant turn's `tool_calls` with the
         *     `tool` turns that answer them by exactly this string, and a conversation
         *     missing one is refused.
         *
         *     `confirmation` is the rule from the domain and not a UI preference, and it
         *     is about REVERSIBILITY. An event — a transaction, a dated valuation — is
         *     verifiable and undone by deleting it, so it gets a light confirmation.
         *     Anything that OVERWRITES gets `diff` and the field-by-field of what would
         *     be replaced: a snapshot, because editing it rewrites what that day said and
         *     every projection anchored after it moves, and equally a questionnaire
         *     answer, which is not kept in history, and after this says something else
         *     and carries another day.
         *
         *     `fingerprint` is what the proposal depended on when it was made, so the
         *     confirmation can tell whether the ground moved under it. See
         *     `tools.Proposal`.
         */
        ChatCardBlock: {
            /** Arguments */
            arguments?: {
                [key: string]: unknown;
            };
            /** Call Id */
            call_id: string;
            /** Card Id */
            card_id: string;
            /**
             * Confirmation
             * @default light
             * @enum {string}
             */
            confirmation?: "light" | "diff";
            /**
             * Consequence
             * @description What confirming this costs that the diff does not show, in the proposing tool's own words. Only the tool knows: editing a snapshot moves every figure anchored after it, while replacing a questionnaire answer moves nothing and simply loses the old one. Empty falls back to the one thing true of every diff card — that it replaces what is on record and the old value does not come back.
             * @default
             */
            consequence?: string;
            /** Diff */
            diff?: components["schemas"]["ChatCardChange"][];
            /**
             * Done
             * @description What a confirmed card says it is now: 'Recorded', 'Added to your watchlist'
             * @default
             */
            done?: string;
            /**
             * Fields
             * @description The proposal's arguments in the reader's words, the absent ones left out
             */
            fields?: components["schemas"]["ChatCardField"][];
            /**
             * Fingerprint
             * @default
             */
            fingerprint?: string;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "card";
            /**
             * Outcome
             * @default pending
             * @enum {string}
             */
            outcome?: "pending" | "confirmed" | "rejected" | "stale";
            /**
             * Receipt
             * @description What a confirmed card wrote, in the reader's words; empty until then
             */
            receipt?: components["schemas"]["ChatCardField"][];
            /**
             * Result
             * @description What the write produced, once it ran — the fields as the tool returned them, not a sentence about them. Two readers want this and they want it in the same shape: the model, which is handed it back as the answer to its call, and the card, which shows it under the diff in the same field-by-field form the diff used. Rendered to a string here it would have to be parsed back for one of them.
             */
            result?: {
                [key: string]: unknown;
            } | null;
            /** Title */
            title: string;
            /** Tool */
            tool: string;
            /**
             * Verb
             * @description What pressing the accept button DOES, in the proposing tool's own words — 'Add to watchlist' rather than 'Confirm'. Empty means Confirm, which is right for everything that writes to the reader's records. It is the tool's word for the same reason `consequence` is: a suggestion changes nothing about their money, and 'Confirm' over a card naming a security reads as approval of a purchase that is not being proposed.
             * @default
             */
            verb?: string;
            /**
             * Warning
             * @description What the card says, in a band of its own while it waits, of a model it would call that OpenRouter's list dates, has passed the day of, or no longer has, with where that model is set. Only the analysis's card calls a model; empty on every other
             * @default
             */
            warning?: string;
        };
        /**
         * ChatCardChange
         * @description One line of a card's diff: what a field says now, and what it would say.
         *
         *     Both sides are TEXT and not numbers, because a diff is read and not
         *     computed with. `now` is null where the record says nothing yet, which is a
         *     different thing from a zero and has to look different.
         */
        ChatCardChange: {
            /** Field */
            field: string;
            /** Now */
            now?: string | null;
            /** Proposed */
            proposed?: string | null;
        };
        /**
         * ChatCardDecision
         * @description The reader's answer to one card.
         *
         *     Deliberately not named `...Create`: it creates nothing, and the contract
         *     test parametrizes every schema whose name ends that way. `ChatRequest` set
         *     that precedent for a chat body already.
         *
         *     Only a decision, and no corrected arguments. Deferred once already,
         *     against the fake tool, and now decided
         *     against the three real ones, so it is a decision rather than a gap.
         *
         *     A card's `arguments` are an untyped dict, because one block type carries
         *     every tool's proposal. An editor over that can only guess its widget from
         *     the runtime type of the JSON value, and every field that is worth
         *     correcting is exactly where that guess fails: a date is a string, a
         *     currency is a string, an asset class is a string with six legal values, and
         *     an institution is a name that has to resolve against a row. So an editable
         *     card either asks the reader to hand-type what the tool exists to resolve
         *     for them, or the card has to carry per-field metadata — which is the
         *     argument schema, declared a second time, in the one place `tools.py` opens
         *     by refusing to declare anything twice.
         *
         *     The correction that does work today costs one round trip and has a single
         *     author: "no, 450" and the model draws a fresh card. When editing is built
         *     it should come from the argument model's own JSON schema, generated where
         *     the tool schema is generated, and that is a design and not a field.
         */
        ChatCardDecision: {
            /**
             * Decision
             * @enum {string}
             */
            decision: "confirm" | "reject";
            /**
             * Model
             * @description OpenRouter slug for the follow-up; empty means the chat default
             */
            model?: string | null;
        };
        /**
         * ChatCardField
         * @description One line of a card as the reader reads it: a label in their words and a
         *     value, never a schema name, a row id or a timestamp (brief AJ: the
         *     reader's cards said "based_on", "symbol null", a row's id, and an ISO
         *     timestamp under "added_at"). `kind` says how the panel writes
         *     the value in the reader's language: a day ("date", YYYY-MM-DD), a number,
         *     or an amount in `currency`.
         */
        ChatCardField: {
            /** Currency */
            currency?: string | null;
            /**
             * Kind
             * @default text
             * @enum {string}
             */
            kind?: "text" | "date" | "number" | "amount";
            /** Label */
            label: string;
            /** Value */
            value: string;
        };
        /**
         * ChatConversationDetail
         * @description The conversation with every turn, oldest first.
         */
        ChatConversationDetail: {
            /** Created At */
            created_at: string;
            /** Id */
            id: number;
            /** Messages */
            messages: components["schemas"]["ChatMessageRead"][];
            /** Title */
            title: string | null;
            /** Updated At */
            updated_at: string;
        };
        /**
         * ChatConversationRead
         * @description A conversation as the history list shows it: its first question as the
         *     title, and when it was last spoken to.
         */
        ChatConversationRead: {
            /** Created At */
            created_at: string;
            /** Id */
            id: number;
            /** Title */
            title: string | null;
            /** Updated At */
            updated_at: string;
        };
        /**
         * ChatDecided
         * @description A card has been decided, and this is the card as it is now stored.
         *
         *     Sent the moment the decision is on record: right after `start` for every
         *     card but the analyzer's, whose decision is stored when its run is, after
         *     its steps. The panel swaps the card it shows for this one there and then,
         *     so the card reads as decided whatever the turn that follows does. Until
         *     brief AJ the panel coloured it only once that turn had ended well: the
         *     reader's second confirmation, on 2026-10-08, was stored, its follow-up
         *     failed, and the card kept its buttons; pressing again was refused as a
         *     decision already taken. The block itself, for the reason `ChatCard`
         *     carries one: one shape, whether it arrived now or is read back later.
         */
        ChatDecided: {
            card: components["schemas"]["ChatCardBlock"];
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "decided";
        };
        /**
         * ChatDelta
         * @description A piece of the answer, in order. Concatenate them.
         */
        ChatDelta: {
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "delta";
            /** Text */
            text: string;
        };
        /**
         * ChatDone
         * @description The answer is complete and stored. Its ABSENCE is the signal: a stream
         *     that ends without this event broke off, and the client must say so rather
         *     than show a truncated answer as though it were the whole one.
         */
        ChatDone: {
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "done";
            /** Message Id */
            message_id: number;
            /** Model */
            model: string;
        };
        /**
         * ChatError
         * @description The answer cannot continue, and why. Sent in place of `done`.
         */
        ChatError: {
            /** Detail */
            detail: string;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "error";
        };
        /**
         * ChatMessageRead
         * @description One stored turn. `status` is how an assistant turn ENDED — done, error
         *     (with `detail`), or cut, the connection closed before it finished — and
         *     null on a user turn.
         */
        ChatMessageRead: {
            /** Blocks */
            blocks: (components["schemas"]["ChatTextBlock"] | components["schemas"]["ChatThoughtBlock"] | components["schemas"]["ChatPageBlock"] | components["schemas"]["ChatToolBlock"] | components["schemas"]["ChatSourcesBlock"] | components["schemas"]["ChatCardBlock"])[];
            /** Created At */
            created_at: string;
            /** Detail */
            detail: string | null;
            /** Id */
            id: number;
            /** Model */
            model: string | null;
            /** Role */
            role: string;
            /** Seq */
            seq: number;
            /** Status */
            status: string | null;
        };
        /**
         * ChatModel
         * @description One entry of the model dropdown.
         */
        ChatModel: {
            /**
             * Listed
             * @description Whether today's read of OpenRouter's public list has the model; null when the list has not been read today. One it lacks is still offered, marked: a name that had left the list was seen still answering
             */
            listed: boolean | null;
            /**
             * Note
             * @description What is known about it, with the date it was checked
             */
            note: string | null;
            /**
             * Retires
             * @description The day after which OpenRouter's public list says the model may be removed (its `expiration_date`), as read today; null when the list gives it none, or has not been read today
             */
            retires: string | null;
            /**
             * Searches
             * @description Whether a question to this model may search the web, which runs on a model of its own (`search_warning`)
             * @default false
             */
            searches: boolean;
            /** Slug */
            slug: string;
            /**
             * Warning
             * @description What the panel says above the question box while this model is the one a question goes to: that OpenRouter's list dates it within `model_list.WARN_DAYS` days, or on a day already past, or no longer has it; with where it is set and how to change it. Null when there is nothing to say
             */
            warning: string | null;
        };
        /**
         * ChatModelsRead
         * @description What the dropdown offers, and which of them answers when nothing is picked.
         */
        ChatModelsRead: {
            /** Default */
            default: string;
            /** Models */
            models: components["schemas"]["ChatModel"][];
            /**
             * Search Warning
             * @description What the panel says of the web search's model, with a model that `searches`: dated, past its day, or no longer listed, as a model's `warning`. Null when there is nothing to say
             */
            search_warning: string | null;
        };
        /**
         * ChatPageAccount
         * @description One institution's page: its cash register and its situations.
         */
        ChatPageAccount: {
            /** Institution Id */
            institution_id: number;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "account";
        };
        /**
         * ChatPageAnalyses
         * @description The list of every analysis run.
         */
        ChatPageAnalyses: {
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "analyses";
        };
        /**
         * ChatPageAnalysis
         * @description One analysis run, open in the main column.
         */
        ChatPageAnalysis: {
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "analysis";
            /** Run Id */
            run_id: number;
        };
        /**
         * ChatPageBlock
         * @description Where in the app the reader was when they asked — kept on the question,
         *     before its words.
         *
         *     A NAME and not an id, fixed at the moment of asking: "Records → Wealth →
         *     Broker B". The reader moves between messages, so where they are now says
         *     nothing about where an earlier question was asked, and a conversation that
         *     renamed its past when an account was renamed would be rewriting what was
         *     said. The same reason a sum fixed on a day is never restated.
         *
         *     It is the APP's sentence, never the reader's, which is why it is a block of
         *     its own rather than a line pasted into their text. See `app/screen.py`.
         */
        ChatPageBlock: {
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "page";
            /** Label */
            label: string;
        };
        /** ChatPageDashboard */
        ChatPageDashboard: {
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "dashboard";
        };
        /**
         * ChatPageDebt
         * @description One debt's page: its outstanding balance over time.
         */
        ChatPageDebt: {
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "debt";
            /** Liability Id */
            liability_id: number;
        };
        /** ChatPagePortfolio */
        ChatPagePortfolio: {
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "portfolio";
        };
        /** ChatPageProfile */
        ChatPageProfile: {
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "profile";
        };
        /**
         * ChatPageRealAsset
         * @description One real asset's page: its dated valuations.
         */
        ChatPageRealAsset: {
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "real_asset";
            /** Real Asset Id */
            real_asset_id: number;
        };
        /**
         * ChatPageRecords
         * @description A sub-page of Records with nothing opened inside it.
         */
        ChatPageRecords: {
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "records";
            /**
             * Section
             * @enum {string}
             */
            section: "wealth" | "real" | "debts" | "cash";
        };
        /**
         * ChatPageSituation
         * @description One dated situation, opened from its account's page.
         */
        ChatPageSituation: {
            /** Institution Id */
            institution_id: number;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "situation";
            /** Snapshot Id */
            snapshot_id: number;
        };
        /**
         * ChatRequest
         * @description One more question in a conversation.
         *
         *     The server holds the conversation, so the client sends only the new
         *     question and which conversation it belongs to — none, and a new one is
         *     opened for it. The financial context is rebuilt from the database on each
         *     request, so what the model reads is never older than the question.
         */
        ChatRequest: {
            /** Content */
            content: string;
            /**
             * Conversation Id
             * @description Continue this conversation; null opens a new one
             */
            conversation_id?: number | null;
            /**
             * Model
             * @description OpenRouter slug; empty means the configured chat default
             */
            model?: string | null;
            /**
             * Page
             * @description The page on screen when this was sent. A hint about what 'this' refers to, never a narrowing of the question; null says nothing
             */
            page?: (components["schemas"]["ChatPageDashboard"] | components["schemas"]["ChatPagePortfolio"] | components["schemas"]["ChatPageProfile"] | components["schemas"]["ChatPageRecords"] | components["schemas"]["ChatPageAccount"] | components["schemas"]["ChatPageSituation"] | components["schemas"]["ChatPageRealAsset"] | components["schemas"]["ChatPageDebt"] | components["schemas"]["ChatPageAnalyses"] | components["schemas"]["ChatPageAnalysis"]) | null;
        };
        /**
         * ChatSources
         * @description What one web search found, as it comes back: the query the app sent
         *     and the pages it found, in one piece, since the search's answer arrives
         *     whole.
         *
         *     Sent under the search's line and before the words written from it. The
         *     panel puts it where it arrived, as the stored `ChatSourcesBlock` will be
         *     when the conversation is read back.
         */
        ChatSources: {
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "sources";
            /** Pages */
            pages: components["schemas"]["ChatWebPage"][];
            /** Query */
            query: string;
        };
        /**
         * ChatSourcesBlock
         * @description The pages one web search found, under the query it was asked with,
         *     kept where the search ran.
         *
         *     Provenance, for the reason a `ChatToolBlock` is kept: an answer that says
         *     "Vanguard gives 0.03%" got that from somewhere, and the reader is owed the
         *     page. These are what the search RETURNED (the app's search, on Exa through
         *     OpenRouter, hands back every page it found, five a search), so they are
         *     the pages the model was given to read, not a claim about which of them it
         *     used; the sentence that uses one carries its link.
         *
         *     The query since brief AM (2026-10-09): the app runs each search itself, so
         *     it knows the query it sent, and the reader is shown it above the pages:
         *     what went out of the app to be searched for. Each search is a list of its
         *     own; an empty one is a search that ran and found nothing.
         *     A block stored before has no query. Never sent back to the model with a
         *     later turn: past turns travel as their words, and a link the model wrote
         *     travels inside them.
         */
        ChatSourcesBlock: {
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "sources";
            /** Pages */
            pages: components["schemas"]["ChatWebPage"][];
            /**
             * Query
             * @description What the app sent to be searched for; null on a list stored before brief AM
             */
            query?: string | null;
        };
        /**
         * ChatStart
         * @description The first frame: which conversation this turn landed in — the id a new
         *     conversation was given — and the stored id of the question.
         *
         *     Null where there was no question. Answering a card resumes a conversation
         *     without anybody asking anything: the reader pressed confirm, and inventing
         *     a user turn to hang the id on would put a sentence in their mouth that
         *     they never wrote.
         *
         *     `page_label` is where the question was stored as asked from, as the server
         *     resolved it — a page gone since has already climbed a level. It arrives
         *     before the answer so the panel can print it under the question while the
         *     answer is still being written, from the one authority on it rather than
         *     from a guess of its own.
         */
        ChatStart: {
            /** Conversation Id */
            conversation_id: number;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "start";
            /** Page Label */
            page_label?: string | null;
            /** User Message Id */
            user_message_id?: number | null;
        };
        /**
         * ChatStep
         * @description A long tool has finished one of its steps, and is going on.
         *
         *     Sent while it runs, and never stored. Its job is `ChatTool`'s job said more
         *     than once: to be what the silence IS. The analyzer is three to six steps,
         *     the analyst's in up to four requests each, and minutes of them, and the
         *     page it used to live on refused to fake
         *     a progress bar for exactly the right reason — `run_chain` wrote nothing
         *     until all of it had finished, so "step 2 of 4" would have been invented.
         *     Now each finished step is a fact the orchestrator was told, so it can be
         *     said without inventing anything.
         *
         *     Nothing here is a record. What is persisted is the run itself, whole, at
         *     the end — and the card that proposed it becomes the receipt. A second copy
         *     of "the analyst finished at 12s" inside the message blocks would be a third
         *     place the same run lives.
         */
        ChatStep: {
            /** Duration Ms */
            duration_ms: number;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "step";
            /** Label */
            label: string;
            /** Step No */
            step_no: number;
            /** Tool */
            tool: string;
        };
        /**
         * ChatTextBlock
         * @description A run of text in a message.
         */
        ChatTextBlock: {
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "text";
            /** Text */
            text: string;
        };
        /**
         * ChatThought
         * @description A piece of the model's reasoning, in order, before the answer starts.
         *     Shown folded and quiet: it is how the wait is spent, not the answer.
         */
        ChatThought: {
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "thought";
            /** Text */
            text: string;
        };
        /**
         * ChatThoughtBlock
         * @description The model's reasoning before it answered — kept, folded, so the reader
         *     can see how the answer was reached, and never sent back to the model.
         */
        ChatThoughtBlock: {
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "thought";
            /** Text */
            text: string;
        };
        /**
         * ChatTool
         * @description A tool has been asked for and is running.
         *
         *     Sent BEFORE the tool runs, not after, because its whole job is to say what
         *     the silence is. The look-through reads a cache in milliseconds and walks
         *     four fund issuers when the cache is cold, and the difference between those
         *     two is the difference between a pause and a minute — the same argument
         *     that put the model's own thinking on the wire rather than leaving a
         *     spinner. How it WENT is not here: it is in the stored `ChatToolBlock`, and
         *     in the answer the model writes next.
         *
         *     Except a failure, since brief AG (2026-10-06). The loop answers a call
         *     before it sends this, so a refusal is known by then, and `detail` carries
         *     its reason, as the stored block keeps it: a suggestion past the third in
         *     one answer, or one Yahoo could not vouch for, arrives in a round that ends
         *     on the cards it did draw, where the model never gets to say why it is
         *     missing. Null when nothing failed, which is not a claim that anything
         *     succeeded.
         */
        ChatTool: {
            /** Detail */
            detail?: string | null;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "tool";
            /** Name */
            name: string;
        };
        /**
         * ChatToolBlock
         * @description A tool the model consulted while writing this answer, kept in the place
         *     it was consulted.
         *
         *     It is here for provenance, which is the same reason every figure on this
         *     reader's screen carries where it came from. An answer that says "counting
         *     inside your funds, NVIDIA is 4.2% of the portfolio" got that from
         *     somewhere, and a stored answer that does not say so is the one number on
         *     the screen that cannot be traced. `ok` is false when the tool refused or
         *     broke, and `detail` says why: an answer written after a tool failed was
         *     written with less than it asked for, and the reader is owed that.
         *
         *     `call_id` and `arguments` are the call as the model made it, kept so a
         *     later turn reads what this answer called (`chat._wire`, brief AN): the
         *     chat had retracted true statements on finding no trace of its own
         *     lookups. Absent on the blocks stored before, and `arguments` on a call
         *     whose arguments were not a JSON object.
         */
        ChatToolBlock: {
            /** Arguments */
            arguments?: {
                [key: string]: unknown;
            } | null;
            /** Call Id */
            call_id?: string | null;
            /** Detail */
            detail?: string | null;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "tool";
            /** Name */
            name: string;
            /** Ok */
            ok: boolean;
        };
        /**
         * ChatWebPage
         * @description One page a web search found: its address and its title. An http or https
         *     address only, checked where it entered (`websearch._page`), because it is
         *     shown as a link the reader can press.
         */
        ChatWebPage: {
            /** Title */
            title: string;
            /** Url */
            url: string;
        };
        /**
         * CompositionRow
         * @description Look-through status of one portfolio position: what it resolved to,
         *     which source decomposed it, or why it stayed whole.
         */
        CompositionRow: {
            /** Asset Class */
            asset_class: string | null;
            /** Asset Name */
            asset_name: string;
            /** Decomposed */
            decomposed: boolean;
            /** Error */
            error: string | null;
            /** Fetched At */
            fetched_at: string | null;
            /** Holdings Count */
            holdings_count: number | null;
            /** Isin */
            isin: string | null;
            /** Resolved Name */
            resolved_name: string | null;
            /**
             * Source
             * @description justetf | mstarpy | yfinance
             */
            source: string | null;
            /** Symbol */
            symbol: string | null;
            /** Weight Pct */
            weight_pct: number;
        };
        /**
         * DashboardAllocation
         * @description Top-level financial-vs-real split, with per-class / per-category detail.
         */
        DashboardAllocation: {
            /**
             * Base Currency
             * @description The currency this payload's computed amounts are in — the database's base, as the figures were converted. Figures a row states itself (an anchor, a transaction, a valuation) keep their own `currency`.
             */
            base_currency: string;
            /** By Asset Class */
            by_asset_class: components["schemas"]["AssetClassSlice"][];
            /** By Real Category */
            by_real_category: components["schemas"]["RealCategorySlice"][];
            /** Financial Total */
            financial_total: number;
            /** Real Total */
            real_total: number;
            /**
             * Unconverted
             * @description The codes counted here as written (`UnconvertedCode`); a slice's share is under "class:<asset class>" or "category:<category>".
             */
            unconverted: components["schemas"]["UnconvertedCode"][];
        };
        /**
         * DashboardSummary
         * @description Net worth = financial + real − liabilities, plus the splits and counts.
         *
         *     financial_total = investments_total (snapshots, ex-cash) + cash_total
         *     (the live cash register projected to today). liabilities_total = sum of
         *     the latest outstanding balance of each debt.
         */
        DashboardSummary: {
            /** As Of */
            as_of: string | null;
            /**
             * Base Currency
             * @description The currency this payload's computed amounts are in — the database's base, as the figures were converted. Figures a row states itself (an anchor, a transaction, a valuation) keep their own `currency`.
             */
            base_currency: string;
            /** Cash Total */
            cash_total: number;
            /**
             * Declared Instead
             * @description What those same situations declared that the app was not expecting. Three summary rows replaced by twenty-one positions is a portfolio described better, not their value lost, and naming only the first half cannot tell the reader which it is.
             */
            declared_instead: components["schemas"]["ArrivedPosition"][];
            /** Financial Total */
            financial_total: number;
            /** Institutions */
            institutions: number;
            /**
             * Investments At Book
             * @description How much of it is carried over from the last photograph instead
             * @default 0
             */
            investments_at_book: number;
            /**
             * Investments At Market
             * @description How much of the investment total the market actually priced
             * @default 0
             */
            investments_at_market: number;
            /** Investments Total */
            investments_total: number;
            /** Liabilities */
            liabilities: number;
            /** Liabilities Total */
            liabilities_total: number;
            /** Net Worth */
            net_worth: number;
            /** Real Assets */
            real_assets: number;
            /** Real Total */
            real_total: number;
            /**
             * Unconverted
             * @description The codes that entered these totals as written, because no rate converts them, said instead of passing in silence: what kind of code, where it is written, and how much of each total it is.
             */
            unconverted: components["schemas"]["UnconvertedCode"][];
            /**
             * Unresolved Omissions
             * @description Value that left the totals because a newer photograph did not mention it. Selling is an assertion with a date and proceeds; forgetting is the absence of one, and the app must not let the difference pass in silence.
             */
            unresolved_omissions: components["schemas"]["OmittedPosition"][];
        };
        /**
         * DeletionRead
         * @description What deleting a row does, in words, asked by a page before it deletes
         *     it: the sentences the chat's card says for the same deletion (brief AP,
         *     `cash_moves`).
         */
        DeletionRead: {
            /** Said */
            said: string;
        };
        /**
         * DividendAnswer
         * @description The reader's answer to a question the catch-up asked (brief AZ).
         *
         *     `link`: the entry `transaction_id` is the dividend with `ex_date` (the
         *     app's estimate of it, if any, goes). `apart`: each pair in `pairs` is not
         *     one dividend, and the two are never paired again. `in_balance` and
         *     `after_balance`: the money of the dividend with `ex_date` was already in
         *     the balance of `balance_date`, or came after it.
         */
        DividendAnswer: {
            /**
             * Answer
             * @enum {string}
             */
            answer: "link" | "apart" | "in_balance" | "after_balance";
            /** Balance Date */
            balance_date?: string | null;
            /** Ex Date */
            ex_date?: string | null;
            /** Institution Id */
            institution_id: number;
            /** Pairs */
            pairs?: components["schemas"]["DividendPairIn"][];
            /** Symbol */
            symbol: string;
            /** Transaction Id */
            transaction_id?: number | null;
        };
        /**
         * DividendEntryRead
         * @description A dividend row as a question about it names it.
         */
        DividendEntryRead: {
            /** Amount */
            amount: number;
            /** Currency */
            currency: string;
            /** Date */
            date: string;
            /** Estimated */
            estimated: boolean;
            /** Id */
            id: number;
        };
        /**
         * DividendPairIn
         * @description An entry and a dividend the reader says are not one.
         */
        DividendPairIn: {
            /**
             * Ex Date
             * Format: date
             */
            ex_date: string;
            /** Transaction Id */
            transaction_id: number;
        };
        /**
         * DividendQuestion
         * @description Something about a dividend only the reader can say (brief AZ), asked
         *     in the banner until answered, with nothing written meanwhile.
         *
         *     `same_dividend`: an entry of theirs beside the app's estimate of the same
         *     dividend; keep theirs and remove the estimate, or keep both.
         *     `which_entry`: two or more of their entries could be one dividend.
         *     `which_dividend`: one entry could be two or more dividends.
         *     `in_balance`: the account's latest balance, `balance_date`, falls in the
         *     dividend's window and no payment date is known: was its money already in
         *     that balance? `first_situation` is the day of the account's first
         *     situation when the units are that situation's, the ex-date being before
         *     it.
         */
        DividendQuestion: {
            /** Asset Name */
            asset_name: string;
            /** Balance Date */
            balance_date: string | null;
            /** Dividends */
            dividends: components["schemas"]["ListedDividend"][];
            /** Entries */
            entries: components["schemas"]["DividendEntryRead"][];
            /** First Situation */
            first_situation: string | null;
            /** Institution Id */
            institution_id: number;
            /** Institution Name */
            institution_name: string;
            /**
             * Kind
             * @enum {string}
             */
            kind: "same_dividend" | "which_entry" | "which_dividend" | "in_balance";
            /** Symbol */
            symbol: string;
        };
        /**
         * DividendRecognised
         * @description An entry of the reader's the catch-up recognised as a dividend Yahoo
         *     lists (brief AZ): the only entry in that dividend's window, the only
         *     dividend whose window holds it. It took the dividend's ex-date, and the
         *     dividend was not recorded beside it.
         */
        DividendRecognised: {
            entry: components["schemas"]["DividendEntryRead"];
            /** Ex Date */
            ex_date: string;
            /** Institution Id */
            institution_id: number;
            /** Institution Name */
            institution_name: string;
            /** Symbol */
            symbol: string;
        };
        /**
         * DividendWaiting
         * @description A dividend whose payment day Yahoo names and is still ahead (brief AZ):
         *     recorded on that day, and said once meanwhile.
         */
        DividendWaiting: {
            /** Currency */
            currency: string | null;
            /** Dps */
            dps: number | null;
            /** Ex Date */
            ex_date: string;
            /** Institution Id */
            institution_id: number;
            /** Institution Name */
            institution_name: string;
            /** Paid On */
            paid_on: string;
            /** Symbol */
            symbol: string;
        };
        /**
         * ExpenseCreate
         * @description Payload to create an expense.
         */
        ExpenseCreate: {
            /**
             * Amount
             * @description Amount per occurrence
             */
            amount: number;
            /**
             * Category
             * @description housing | food | transport | utilities | health | insurance | debt | leisure | education | other
             */
            category?: string | null;
            /**
             * Currency
             * @description Currency, e.g. EUR
             */
            currency: string;
            /**
             * End Date
             * @description Last occurrence (optional; open-ended if null)
             */
            end_date?: string | null;
            /**
             * Frequency
             * @description monthly | quarterly | semiannual | annual | one_off
             */
            frequency?: string | null;
            /**
             * Institution Id
             * @description Institution whose cash this expense draws from
             */
            institution_id?: number | null;
            /**
             * Name
             * @description Expense name (e.g. 'Rent', 'Groceries')
             */
            name: string;
            /**
             * Nature
             * @description essential | discretionary
             */
            nature?: string | null;
            /**
             * Notes
             * @description Free-form notes
             */
            notes?: string | null;
            /**
             * Start Date
             * @description First occurrence / one-off date (YYYY-MM-DD)
             */
            start_date?: string | null;
        };
        /**
         * ExpenseRead
         * @description Representation of an expense returned by the API.
         */
        ExpenseRead: {
            /**
             * Amount
             * @description Amount per occurrence
             */
            amount: number;
            /**
             * Category
             * @description housing | food | transport | utilities | health | insurance | debt | leisure | education | other
             */
            category: string | null;
            /** Created At */
            created_at: string;
            /**
             * Currency
             * @description Currency, e.g. EUR
             */
            currency: string;
            /**
             * End Date
             * @description Last occurrence (optional; open-ended if null)
             */
            end_date: string | null;
            /**
             * Frequency
             * @description monthly | quarterly | semiannual | annual | one_off
             */
            frequency: string | null;
            /** Id */
            id: number;
            /**
             * Institution Id
             * @description Institution whose cash this expense draws from
             */
            institution_id: number | null;
            /**
             * Name
             * @description Expense name (e.g. 'Rent', 'Groceries')
             */
            name: string;
            /**
             * Nature
             * @description essential | discretionary
             */
            nature: string | null;
            /**
             * Notes
             * @description Free-form notes
             */
            notes: string | null;
            /**
             * Start Date
             * @description First occurrence / one-off date (YYYY-MM-DD)
             */
            start_date: string | null;
        };
        /**
         * FlowNotCounted
         * @description An income or an expense the monthly figures leave out, with the dates
         *     that say why: its first payment is after today, or it has ended. The Cash
         *     flow page marks its own row by `side` and `id`.
         */
        FlowNotCounted: {
            /** End Date */
            end_date: string | null;
            /** Frequency */
            frequency: string | null;
            /** Id */
            id: number;
            /** Name */
            name: string;
            /**
             * Side
             * @enum {string}
             */
            side: "income" | "expense";
            /** Start Date */
            start_date: string | null;
        };
        /**
         * FxRateRead
         * @description One ECB reference rate: units of `currency` per 1 `base` on `as_of`.
         */
        FxRateRead: {
            /** As Of */
            as_of: string;
            /** Base */
            base: string;
            /** Currency */
            currency: string;
            /** Fetched At */
            fetched_at: string;
            /** Rate */
            rate: number;
        };
        /**
         * GoalCreate
         * @description Payload to create a goal.
         */
        GoalCreate: {
            /**
             * Currency
             * @description Currency, e.g. EUR
             */
            currency: string;
            /** Current Amount */
            current_amount?: number | null;
            /** Monthly Contribution */
            monthly_contribution?: number | null;
            /** Name */
            name: string;
            /** Notes */
            notes?: string | null;
            /** Target Amount */
            target_amount?: number | null;
            /** Target Date */
            target_date?: string | null;
            /** Type */
            type?: string | null;
        };
        /**
         * GoalRead
         * @description A stored goal as returned by the API.
         */
        GoalRead: {
            /** Created At */
            created_at: string;
            /**
             * Currency
             * @description Currency, e.g. EUR
             */
            currency: string;
            /** Current Amount */
            current_amount: number | null;
            /** Id */
            id: number;
            /** Monthly Contribution */
            monthly_contribution: number | null;
            /** Name */
            name: string;
            /** Notes */
            notes: string | null;
            /** Target Amount */
            target_amount: number | null;
            /** Target Date */
            target_date: string | null;
            /** Type */
            type: string | null;
        };
        /**
         * HoldingCreate
         * @description Payload to create a holding. snapshot_id comes from the URL.
         */
        HoldingCreate: {
            /**
             * Asset Class
             * @description Asset class
             */
            asset_class?: string | null;
            /**
             * Asset Name
             * @description Instrument/asset name
             */
            asset_name: string;
            /**
             * Cost Basis
             * @description What the position cost, in this holding's currency. Null means unknown — and unknown stays unknown rather than being inferred from `value`, which is a valuation, not a price paid.
             */
            cost_basis?: number | null;
            /**
             * Cost Estimated
             * @description True when the cost was derived (e.g. from a reported % return)
             */
            cost_estimated?: boolean | null;
            /**
             * Cost Quantity
             * @description How many of the row's units `cost_basis` paid for, when not all of them: a new situation started from the last writes it for a row partly bought since the previous one, the other units being the situation's value. Null means the cost covers every unit. Needs a cost and a quantity, and no more than the quantity.
             */
            cost_quantity?: number | null;
            /**
             * Currency
             * @description Currency, e.g. EUR
             */
            currency: string;
            /**
             * Distribution Policy
             * @description acc | dist (accumulating vs distributing). Left empty, the ticker's own dividend history decides: whatever it pays is recorded, as for a share, which has no policy to choose
             */
            distribution_policy?: string | null;
            /**
             * Isin
             * @description Fund ISIN — what the look-through sources key on
             */
            isin?: string | null;
            /** Quantity */
            quantity?: number | null;
            /**
             * Symbol
             * @description Yahoo ticker used for prices (e.g. VWCE.MI)
             */
            symbol?: string | null;
            /** Unit Price */
            unit_price?: number | null;
            /**
             * Value
             * @description Position value. If absent but quantity and unit_price are set, it is computed.
             */
            value?: number | null;
        };
        /**
         * HoldingRead
         * @description Representation of a holding returned by the API.
         *
         *     Two figures for one row, and they are different facts. `value` is what the
         *     reader TYPED, in `currency`, and it is what the edit form must put back in
         *     the box. `value_base` is what that is worth in the app's base currency, and
         *     it is the only one of the two that may be added to another row.
         */
        HoldingRead: {
            /**
             * Asset Class
             * @description Asset class
             */
            asset_class: string | null;
            /**
             * Asset Name
             * @description Instrument/asset name
             */
            asset_name: string;
            /**
             * Base Currency
             * @description The currency this payload's computed amounts are in — the database's base, as the figures were converted. Figures a row states itself (an anchor, a transaction, a valuation) keep their own `currency`.
             */
            base_currency: string;
            /**
             * Cost Basis
             * @description What the position cost, in this holding's currency. Null means unknown — and unknown stays unknown rather than being inferred from `value`, which is a valuation, not a price paid.
             */
            cost_basis: number | null;
            /**
             * Cost Estimated
             * @description True when the cost was derived (e.g. from a reported % return)
             */
            cost_estimated: boolean | null;
            /**
             * Cost Quantity
             * @description How many of the row's units `cost_basis` paid for, when not all of them: a new situation started from the last writes it for a row partly bought since the previous one, the other units being the situation's value. Null means the cost covers every unit. Needs a cost and a quantity, and no more than the quantity.
             */
            cost_quantity: number | null;
            /**
             * Currency
             * @description Currency, e.g. EUR
             */
            currency: string;
            /**
             * Distribution Policy
             * @description acc | dist (accumulating vs distributing). Left empty, the ticker's own dividend history decides: whatever it pays is recorded, as for a share, which has no policy to choose
             */
            distribution_policy: string | null;
            /** Id */
            id: number;
            /**
             * Isin
             * @description Fund ISIN — what the look-through sources key on
             */
            isin: string | null;
            /**
             * Last Dividend
             * @description The latest ex-date Yahoo lists for this holding's ticker, from the dividend answers the catch-up keeps; null when it was never asked about or lists none. What the line says when no policy is stated and the ticker's own history decides its dividends.
             */
            last_dividend: string | null;
            /** Quantity */
            quantity: number | null;
            /** Snapshot Id */
            snapshot_id: number;
            /**
             * Symbol
             * @description Yahoo ticker used for prices (e.g. VWCE.MI)
             */
            symbol: string | null;
            /**
             * Unconverted
             * @description The code `value_base` is in as written, when no rate converts it, so the row says it is not in `base_currency` (brief BA); null when it was converted.
             */
            unconverted: string | null;
            /** Unit Price */
            unit_price: number | null;
            /**
             * Value
             * @description Position value. If absent but quantity and unit_price are set, it is computed.
             */
            value: number | null;
            /**
             * Value Base
             * @description `value` in `base_currency`, at the ECB rate (Yahoo's for a currency the ECB does not publish), by the ticker's listing currency where it has one, by `currency` otherwise. The figure to display and to total; `value` is the one to edit.
             */
            value_base: number;
        };
        /** HTTPValidationError */
        HTTPValidationError: {
            /** Detail */
            detail?: components["schemas"]["ValidationError"][];
        };
        /**
         * IncomeSourceCreate
         * @description Payload to create an income source.
         */
        IncomeSourceCreate: {
            /**
             * Amount
             * @description Amount per occurrence
             */
            amount: number;
            /**
             * Category
             * @description salary | freelance | business | rental | dividends | interest | pension | other
             */
            category?: string | null;
            /**
             * Currency
             * @description Currency, e.g. EUR
             */
            currency: string;
            /**
             * End Date
             * @description Last occurrence (optional; open-ended if null)
             */
            end_date?: string | null;
            /**
             * Frequency
             * @description monthly | quarterly | semiannual | annual | one_off
             */
            frequency?: string | null;
            /**
             * Institution Id
             * @description Institution whose cash this income feeds
             */
            institution_id?: number | null;
            /**
             * Kind
             * @description active | passive
             */
            kind?: string | null;
            /**
             * Name
             * @description Income source name (e.g. 'Salary', 'Apartment rent')
             */
            name: string;
            /**
             * Notes
             * @description Free-form notes
             */
            notes?: string | null;
            /**
             * Start Date
             * @description First occurrence / one-off date (YYYY-MM-DD)
             */
            start_date?: string | null;
        };
        /**
         * IncomeSourceRead
         * @description Representation of an income source returned by the API.
         */
        IncomeSourceRead: {
            /**
             * Amount
             * @description Amount per occurrence
             */
            amount: number;
            /**
             * Category
             * @description salary | freelance | business | rental | dividends | interest | pension | other
             */
            category: string | null;
            /** Created At */
            created_at: string;
            /**
             * Currency
             * @description Currency, e.g. EUR
             */
            currency: string;
            /**
             * End Date
             * @description Last occurrence (optional; open-ended if null)
             */
            end_date: string | null;
            /**
             * Frequency
             * @description monthly | quarterly | semiannual | annual | one_off
             */
            frequency: string | null;
            /** Id */
            id: number;
            /**
             * Institution Id
             * @description Institution whose cash this income feeds
             */
            institution_id: number | null;
            /**
             * Kind
             * @description active | passive
             */
            kind: string | null;
            /**
             * Name
             * @description Income source name (e.g. 'Salary', 'Apartment rent')
             */
            name: string;
            /**
             * Notes
             * @description Free-form notes
             */
            notes: string | null;
            /**
             * Start Date
             * @description First occurrence / one-off date (YYYY-MM-DD)
             */
            start_date: string | null;
        };
        /**
         * InstitutionCreate
         * @description Payload to create an institution (POST).
         */
        InstitutionCreate: {
            /**
             * Name
             * @description Institution name
             */
            name: string;
            /**
             * Notes
             * @description Free-form notes
             */
            notes?: string | null;
            /**
             * Type
             * @description Institution type
             */
            type?: string | null;
        };
        /**
         * InstitutionRead
         * @description Representation returned by the API (output).
         */
        InstitutionRead: {
            /** Created At */
            created_at: string;
            /** Id */
            id: number;
            /** Latest Snapshot */
            latest_snapshot: string | null;
            /**
             * Name
             * @description Institution name
             */
            name: string;
            /**
             * Notes
             * @description Free-form notes
             */
            notes: string | null;
            /**
             * Snapshot Count
             * @description How much history this institution actually has. One situation is a state worth naming: nothing to compare against, and every quantity as old as that single day.
             * @default 0
             */
            snapshot_count: number;
            /**
             * Type
             * @description Institution type
             */
            type: string | null;
        };
        /**
         * InstrumentFamily
         * @description The same fund in its accumulating and distributing forms, together.
         */
        InstrumentFamily: {
            /** Key */
            key: string;
            /** Members */
            members: components["schemas"]["InstrumentMember"][];
        };
        /**
         * InstrumentMember
         * @description One instrument in the registry.
         *
         *     `base_ticker` is NOT a Yahoo symbol and `share_class_currency` is NOT the
         *     currency a holding trades in: the catalogue says EUNL and USD for iShares
         *     Core MSCI World, which Xetra trades in EUR. They are shown to help tell
         *     two similar rows apart, never to fill those fields.
         */
        InstrumentMember: {
            /** Base Ticker */
            base_ticker: string | null;
            /**
             * Distribution Policy
             * @description acc | dist
             */
            distribution_policy: string | null;
            /** Domicile */
            domicile: string | null;
            /** Hedged */
            hedged: boolean | null;
            /** Holdings Count */
            holdings_count: number | null;
            /** Isin */
            isin: string;
            /** Name */
            name: string;
            /** Replication */
            replication: string | null;
            /** Share Class Currency */
            share_class_currency: string | null;
            /** Size Meur */
            size_meur: number | null;
            /** Ter */
            ter: number | null;
        };
        /**
         * InstrumentSearch
         * @description `coverage` says how the match was made: 'all' means every word was
         *     found, 'partial' means the search had to loosen to find anything — a
         *     weaker claim about what was asked for, and the caller is expected to say
         *     so rather than present both the same way.
         */
        InstrumentSearch: {
            /**
             * Coverage
             * @default none
             */
            coverage: string;
            /** Families */
            families: components["schemas"]["InstrumentFamily"][];
            /** Fetched At */
            fetched_at: string | null;
            /** Retry After */
            retry_after: string | null;
            /**
             * Rows
             * @default 0
             */
            rows: number;
            /** Source */
            source: string | null;
            /**
             * State
             * @default ready
             * @enum {string}
             */
            state: "ready" | "downloading" | "failed" | "not_started";
        };
        /**
         * IsinSuggestion
         * @description A best-effort ISIN -> ticker suggestion from OpenFIGI.
         */
        IsinSuggestion: {
            /** Exchange */
            exchange: string | null;
            /** Name */
            name: string | null;
            /** Ticker */
            ticker: string | null;
            /** Type */
            type: string | null;
        };
        /**
         * KillSwitchRequest
         * @description POST /api/trading/kill-switch body. `enabled` is the direction of the
         *     throw: true halts entries desk-wide immediately (protective exits keep
         *     flowing — the switch refuses entries, never safety), false re-arms.
         *     `note` is optional going ON — speed beats paperwork in that direction —
         *     and MANDATORY coming OFF: re-arming a halted desk is the dangerous
         *     direction, and the audit row deserves the operator's own sentence for
         *     why, enforced server-side as a 422, never by browser chrome alone.
         */
        KillSwitchRequest: {
            /** Enabled */
            enabled: boolean;
            /**
             * Note
             * @default
             */
            note?: string;
        };
        /**
         * KillSwitchState
         * @description The switch as persisted — the same truth GET /rails reads live.
         */
        KillSwitchState: {
            /** Note */
            note: string;
            /** Tripped */
            tripped: boolean;
        };
        /**
         * LiabilityBalanceCreate
         * @description Payload to create a balance. liability_id comes from the URL.
         */
        LiabilityBalanceCreate: {
            /**
             * Balance
             * @description Outstanding principal at that date
             */
            balance: number;
            /**
             * Date
             * Format: date
             * @description Balance date (YYYY-MM-DD)
             */
            date: string;
            /**
             * Note
             * @description Free-form notes
             */
            note?: string | null;
        };
        /**
         * LiabilityBalanceRead
         * @description A stored balance as returned by the API.
         */
        LiabilityBalanceRead: {
            /**
             * Balance
             * @description Outstanding principal at that date
             */
            balance: number;
            /** Created At */
            created_at: string;
            /**
             * Date
             * Format: date
             * @description Balance date (YYYY-MM-DD)
             */
            date: string;
            /** Id */
            id: number;
            /** Liability Id */
            liability_id: number;
            /**
             * Note
             * @description Free-form notes
             */
            note: string | null;
        };
        /**
         * LiabilityCreate
         * @description Payload to create a liability.
         */
        LiabilityCreate: {
            /**
             * Currency
             * @description Currency, e.g. EUR
             */
            currency: string;
            /**
             * Interest Rate
             * @description Annual interest rate in % (e.g. 3.2)
             */
            interest_rate?: number | null;
            /**
             * Kind
             * @description Debt kind
             */
            kind?: string | null;
            /**
             * Name
             * @description Debt name (e.g. 'Home mortgage')
             */
            name: string;
            /**
             * Notes
             * @description Free-form notes
             */
            notes?: string | null;
            /**
             * Real Asset Id
             * @description Real asset this debt finances (mortgage -> house)
             */
            real_asset_id?: number | null;
        };
        /**
         * LiabilityRead
         * @description A stored liability. `latest_balance` = most recent outstanding balance.
         */
        LiabilityRead: {
            /** Created At */
            created_at: string;
            /**
             * Currency
             * @description Currency, e.g. EUR
             */
            currency: string;
            /** Id */
            id: number;
            /**
             * Interest Rate
             * @description Annual interest rate in % (e.g. 3.2)
             */
            interest_rate: number | null;
            /**
             * Kind
             * @description Debt kind
             */
            kind: string | null;
            /** Latest Balance */
            latest_balance: number | null;
            /**
             * Name
             * @description Debt name (e.g. 'Home mortgage')
             */
            name: string;
            /**
             * Notes
             * @description Free-form notes
             */
            notes: string | null;
            /**
             * Real Asset Id
             * @description Real asset this debt finances (mortgage -> house)
             */
            real_asset_id: number | null;
        };
        /**
         * ListedDividend
         * @description A dividend Yahoo lists, as a question names it: its ex-date, the
         *     figure a share and its currency, the units held before the ex-date, and
         *     the app's row for it while that row is still the market's estimate.
         */
        ListedDividend: {
            /** Currency */
            currency: string | null;
            /** Dps */
            dps: number | null;
            estimate: components["schemas"]["DividendEntryRead"] | null;
            /** Ex Date */
            ex_date: string;
            /** Units */
            units: number | null;
        };
        /**
         * MatrixCell
         * @description One asset class x region cell of the look-through, as a percent of the
         *     whole portfolio.
         */
        MatrixCell: {
            /** Asset Class */
            asset_class: string;
            /** Pct */
            pct: number;
            /** Region */
            region: string;
        };
        /**
         * NetWorthPoint
         * @description One point of the net-worth-over-time series (net = fin + real − debts).
         */
        NetWorthPoint: {
            /**
             * Base Currency
             * @description The currency this payload's computed amounts are in — the database's base, as the figures were converted. Figures a row states itself (an anchor, a transaction, a valuation) keep their own `currency`.
             */
            base_currency: string;
            /**
             * Date
             * Format: date
             */
            date: string;
            /** Financial */
            financial: number;
            /**
             * Fx As Of
             * @description The ECB day whose rates converted this point, the latest published on or before `date`: for a currency the ECB publishes, or for the dollar a Yahoo close was crossed at. Null when no ECB rate was used.
             */
            fx_as_of: string | null;
            /**
             * Fx Yahoo As Of
             * @description Yahoo's day whose close converted a currency the ECB does not publish at this point (brief BA); null when none was.
             */
            fx_yahoo_as_of: string | null;
            /** Liabilities */
            liabilities: number;
            /** Net Worth */
            net_worth: number;
            /** Real */
            real: number;
            /**
             * Unconverted
             * @description The codes this point counts as written, because no rate converts them. Codes only: what a code is of the net worth is the summary's share at the last point, and a sum over points would count one row once per point (brief BA).
             */
            unconverted: string[];
        };
        /**
         * NotACode
         * @description A row a new situation copied with a currency that is not a currency
         *     code: written before the shape rule, and copied as written (brief BA).
         */
        NotACode: {
            /** Asset Name */
            asset_name: string;
            /**
             * Currency
             * @description The currency as it is written on the row
             */
            currency: string;
        };
        /**
         * OmittedPosition
         * @description Value a situation did not account for, with nothing on record saying
         *     where it went — a position it stopped naming, or units it stopped
         *     claiming.
         */
        OmittedPosition: {
            /** Asset Name */
            asset_name: string;
            /** Dropped On */
            dropped_on: string;
            /** Institution */
            institution: string | null;
            /** Institution Id */
            institution_id: number | null;
            /** Last Seen */
            last_seen: string;
            /** Last Value */
            last_value: number;
            /** Symbol */
            symbol: string | null;
            /**
             * Units Missing
             * @description Units the situation stopped claiming while still naming the row. Null when the whole position went unnamed, which is the difference between 'this is gone' and 'there is less of this than you had'.
             */
            units_missing: number | null;
        };
        /**
         * OverlapItem
         * @description A stock held inside 2+ funds: combined portfolio weight and the funds.
         */
        OverlapItem: {
            /** Funds */
            funds: string[];
            /** Name */
            name: string;
            /** Pct */
            pct: number;
        };
        /**
         * OverviewFund
         * @description The consolidated fund overview (design §8): ledger wealth beside the
         *     engine's own figure, and the reconciliation between the two statements
         *     about the same money.
         *
         *     The consolidated total is LEDGER wealth — the trading account is already
         *     inside it through the broker statement — with the engine's equity never
         *     summed in.
         */
        OverviewFund: {
            reconciliation: components["schemas"]["OverviewReconciliation"];
            total_wealth: components["schemas"]["DashboardSummary"];
            trading_equity: components["schemas"]["OverviewTradingEquity"];
        };
        /**
         * OverviewReconciliation
         * @description Ledger statement vs engine equity for the mapped trading account.
         *
         *     The statement side is the ledger's own reading of the account: projected
         *     positions at market plus projected cash, the same arithmetic that feeds
         *     net worth, plus the date of the last photograph/balance for provenance.
         *     The gap is statement minus engine in the base, and it is None whenever
         *     either side cannot be measured in it — a gap computed on a dollar figure
         *     read as euro would be the wrong answer presented as the right one.
         *
         *     `missing` is the list of what stands between the reader and a gap, as
         *     codes, in the order they would be resolved:
         *     - `no-mapping` — no institution is declared as the trading account;
         *     - `institution-gone` — the declared institution was deleted;
         *     - `no-statement` — the account has no situation and no balance yet;
         *     - `no-engine-equity` — the engine never wrote an equity row;
         *     - `equity-unconvertible` — no rate converts the engine's dollars into the base.
         *     An empty list means the gap is the figure it carries.
         */
        OverviewReconciliation: {
            /**
             * Engine As Of
             * @description Timestamp of the engine row the gap is measured against
             */
            engine_as_of: string | null;
            /**
             * Engine Equity Base
             * @description The engine's equity converted into the base
             */
            engine_equity_base: number | null;
            /**
             * Gap
             * @description statement_total − engine equity, in the base. Signed: positive means the ledger reads more than the engine.
             */
            gap: number | null;
            /** Institution Id */
            institution_id: number | null;
            /** Institution Name */
            institution_name: string | null;
            /**
             * Missing
             * @description What is missing for a gap to exist, as codes; empty means measured
             */
            missing: string[];
            /**
             * Statement Cash
             * @description Projected cash of the account, in the base; None without a balance
             */
            statement_cash: number | null;
            /**
             * Statement Date
             * @description The latest photograph or balance date behind the statement side — how fresh the photograph half of the comparison is
             */
            statement_date: string | null;
            /**
             * Statement Positions
             * @description Projected investment positions of the account, in the base
             */
            statement_positions: number | null;
            /**
             * Statement Total
             * @description Positions + cash in the base. None when the account has no statement at all.
             */
            statement_total: number | null;
        };
        /**
         * OverviewTradingEquity
         * @description What the trading engine last said the desk is worth, engine-reported.
         *
         *     `available` false is a first-class answer — an engine that never ran has
         *     no equity to report, and that is a fact about the desk, not an error. The
         *     figure never enters the net worth: the broker statement already contains
         *     the money, so summing both would count it twice (design D13).
         */
        OverviewTradingEquity: {
            /**
             * As Of
             * @description Timestamp of the latest engine equity row (UTC)
             */
            as_of: string | null;
            /**
             * Available
             * @description False when the engine has written no equity row — never run, or the equity table does not exist in this database. An honest state, not an error.
             */
            available: boolean;
            /**
             * Currency
             * @description The engine's own unit: paper desks trade dollar-quoted pairs
             * @default USD
             */
            currency: string;
            /**
             * Source
             * @description The table the figure is read from — provenance, not decoration
             * @default equity_points
             */
            source: string;
            /**
             * Value
             * @description The latest portfolio equity the engine wrote, in `currency`
             */
            value: number | null;
            /**
             * Value Base
             * @description The same equity in the base currency, when a rate converts it; None when none does. Never a pass-through: a dollar figure is not a euro figure.
             */
            value_base: number | null;
        };
        /**
         * PaidAccept
         * @description The figures the page showed for a row's proposal. The server works the
         *     proposal out again and writes its own figures; these only say which
         *     proposal the reader saw, so a proposal that changed since is refused.
         */
        PaidAccept: {
            /** Paid */
            paid: number;
            /** Units */
            units: number;
        };
        /**
         * PaidAcceptAll
         * @description Every proposal the page showed, accepted at once, in one transaction.
         */
        PaidAcceptAll: {
            /** Rows */
            rows: components["schemas"]["PaidAcceptRow"][];
        };
        /** PaidAcceptRow */
        PaidAcceptRow: {
            /** Holding Id */
            holding_id: number;
            /** Paid */
            paid: number;
            /** Units */
            units: number;
        };
        /**
         * PaidEntry
         * @description An entry of the ledger a proposal read: what it shows under the row.
         */
        PaidEntry: {
            /**
             * Amount
             * @description In the base currency
             */
            amount: number;
            /** Date */
            date: string;
            /**
             * Estimated
             * @description A plan's buy priced at the market close, not yet corrected
             */
            estimated: boolean;
            /**
             * Kind
             * @description buy | sell
             */
            kind: string;
            /** Quantity */
            quantity: number;
        };
        /**
         * PaidNotKept
         * @description A row whose paid part a new situation started from the last could not
         *     keep, because nothing priced the row on that day (brief AV).
         */
        PaidNotKept: {
            /** Asset Name */
            asset_name: string;
            /**
             * Units Paid
             * @description The units that paid part had bought
             */
            units_paid: number;
        };
        /**
         * PaidProposal
         * @description What the ledger paid for a row of an account's latest situation that the
         *     row does not say (brief AW): written as the row's cost only when the reader
         *     accepts it.
         */
        PaidProposal: {
            /** Asset Name */
            asset_name: string;
            /**
             * Entries
             * @description The buys and sells read since `since`, in date order
             */
            entries: components["schemas"]["PaidEntry"][];
            /**
             * Estimated
             * @description Some of it is a plan's buy at the market close, not a contract note
             */
            estimated: boolean;
            /** Holding Id */
            holding_id: number;
            /** Institution */
            institution: string | null;
            /** Institution Id */
            institution_id: number;
            /**
             * Opening Paid
             * @description A cost recorded on that situation, part of `paid`, in the base currency; null when the reading started from no cost
             */
            opening_paid: number | null;
            /** Opening Units */
            opening_units: number | null;
            /**
             * Paid
             * @description What the ledger paid, in the base currency
             */
            paid: number;
            /**
             * Quantity
             * @description The row's units
             */
            quantity: number;
            /** Row Estimated */
            row_estimated: boolean;
            /**
             * Row Paid
             * @description What the row says was paid today, in the base currency: 0 when it states no cost, or a cost a situation started from the last one carried, which this proposal then updates
             */
            row_paid: number;
            /** Row Units */
            row_units: number;
            /**
             * Since
             * @description The situation the ledger was read from
             */
            since: string;
            /**
             * Situation Date
             * @description The latest situation, which holds the row
             */
            situation_date: string;
            /** Symbol */
            symbol: string;
            /**
             * Units
             * @description For how many of the row's units
             */
            units: number;
        };
        /**
         * PlanTargetRead
         * @description A stored plan target as returned by the API.
         */
        PlanTargetRead: {
            /**
             * Asset Name
             * @description Name of the bought instrument (e.g. 'iShares World')
             */
            asset_name: string | null;
            /** Id */
            id: number;
            /**
             * Institution Id
             * @description Institution holding the bought investment
             */
            institution_id: number | null;
            /**
             * Isin
             * @description ISIN of the bought fund, for the look-through
             */
            isin: string | null;
            /** Position */
            position: number;
            /**
             * Symbol
             * @description Ticker of the bought instrument
             */
            symbol: string;
            /**
             * Weight
             * @description Share of the budget. Relative, not absolute: 1/1/1 and 40/30/30 both work.
             * @default 1
             */
            weight: number;
        };
        /**
         * PlanTargetWrite
         * @description One target of a plan a PERSON is writing. See `AccumulationPlanWrite`:
         *     `institution_id` is required here and required nowhere else.
         */
        PlanTargetWrite: {
            /**
             * Asset Name
             * @description Name of the bought instrument (e.g. 'iShares World')
             */
            asset_name?: string | null;
            /**
             * Institution Id
             * @description Where the bought position will be held. Required: a target that names no institution creates a position no situation can ever photograph and no close can settle.
             */
            institution_id: number;
            /**
             * Isin
             * @description ISIN of the bought fund, for the look-through
             */
            isin?: string | null;
            /**
             * Symbol
             * @description Ticker of the bought instrument
             */
            symbol: string;
            /**
             * Weight
             * @description Share of the budget. Relative, not absolute: 1/1/1 and 40/30/30 both work.
             * @default 1
             */
            weight?: number;
        };
        /**
         * Portfolio
         * @description The investment portfolio (latest snapshot of each institution).
         *     `priced` says whether any market prices are shown (freshly fetched or from
         *     the cache); `prices_as_of` is the OLDEST close date among the priced rows,
         *     so the user knows how stale the view can be. `total_realized` /
         *     `total_dividends` sum the gains locked in by sells and the dividends
         *     collected since each account's first situation: every stretch between its
         *     situations, read as each was stored, and what follows the latest (brief
         *     AW). A row's own `realized_pl` and `dividends` cover only what follows its
         *     situation.
         */
        Portfolio: {
            /**
             * Base Currency
             * @description The currency this payload's computed amounts are in — the database's base, as the figures were converted. Figures a row states itself (an anchor, a transaction, a valuation) keep their own `currency`.
             */
            base_currency: string;
            /**
             * Declared Instead
             * @description What those same situations declared that the app was not expecting. Three summary rows replaced by twenty-one positions is a portfolio described better, not their value lost, and naming only the first half cannot tell the reader which it is.
             */
            declared_instead: components["schemas"]["ArrivedPosition"][];
            /**
             * Fx As Of
             * @description ECB reference-rate date, present when an ECB rate was applied: to a currency the ECB publishes, or to the dollar a Yahoo close was crossed at
             */
            fx_as_of: string | null;
            /**
             * Fx Yahoo As Of
             * @description Yahoo's close date, present when a currency the ECB does not publish was converted at Yahoo's rate (brief BA)
             */
            fx_yahoo_as_of: string | null;
            /**
             * Paid Recovery
             * @description What the ledger paid before each account's latest situation that its rows do not say, proposed: written only when the reader accepts it, never proposed again once declined
             */
            paid_recovery: components["schemas"]["PaidProposal"][];
            /**
             * Paid Unread
             * @description Purchases on record left unread because a situation's units disagreed with the ledger's there
             */
            paid_unread: components["schemas"]["UnreadPurchases"][];
            /** Priced */
            priced: boolean;
            /** Prices As Of */
            prices_as_of: string | null;
            /** Rows */
            rows: components["schemas"]["PortfolioRow"][];
            tax_estimate: components["schemas"]["TaxEstimate"];
            /**
             * Total Book
             * @description Sum of what the positions COST
             */
            total_book: number;
            /**
             * Total Book Paid
             * @description Of total_book, the money paid: the rest is situations' values that no purchase price was recorded for (see PortfolioRow.book_paid).
             */
            total_book_paid: number;
            /**
             * Total Dividends
             * @description The dividends collected since each account's first situation; a row's own dividends cover only what follows its situation
             */
            total_dividends: number;
            /**
             * Total Dividends Estimated
             * @description How much of `total_dividends` is still the market's gross figure (see PortfolioRow.dividends_estimated). The remainder is what the reader corrected by hand and is already net.
             */
            total_dividends_estimated: number;
            /**
             * Total Market
             * @description Sum of what they are WORTH: the market price where there is one, the last observed value where there is not. Null when nothing at all is priced. It is deliberately not the sum of the delta column: the rows the market could not price contribute their observation here, and no P/L.
             */
            total_market: number | null;
            /**
             * Total Realized
             * @description What sells and closes realized on the units paid for, since each account's first situation; a row's own realized_pl covers only what follows its situation
             */
            total_realized: number;
            /**
             * Total Realized Movement
             * @description What sells and closes realized on situations' values that no purchase price was recorded for (see PortfolioRow.realized_movement), beside total_realized and never inside it, over the same window
             */
            total_realized_movement: number;
            /**
             * Unconverted
             * @description The codes that entered these totals as written, because no rate converts them, the earlier stretches' dividends and gains included. The pair to `fx_as_of`: that says which rate was applied, this says what no rate could be applied to.
             */
            unconverted: components["schemas"]["UnconvertedCode"][];
            /**
             * Unresolved Omissions
             * @description Positions a newer photograph stopped mentioning: their value left these totals without a line saying where it went.
             */
            unresolved_omissions: components["schemas"]["OmittedPosition"][];
        };
        /**
         * PortfolioComposition
         * @description The portfolio's REAL exposure: per-position resolution rows plus
         *     aggregated country/sector weights and cross-fund holding overlap.
         *     `coverage_pct` = share of the portfolio the look-through decomposed.
         */
        PortfolioComposition: {
            /**
             * Base Currency
             * @description The currency this payload's computed amounts are in — the database's base, as the figures were converted. Figures a row states itself (an anchor, a transaction, a valuation) keep their own `currency`.
             */
            base_currency: string;
            /**
             * Companies
             * @description Single-company exposure through the funds — the same data `overlap` is derived from, but complete instead of only the shared names.
             * @default []
             */
            companies: components["schemas"]["AllocationSlice"][];
            /** Countries */
            countries: components["schemas"]["AllocationSlice"][];
            /** Coverage Pct */
            coverage_pct: number;
            /**
             * Currencies
             * @description Currency the exposure really sits in, derived from the country weights (see app/geo.py for the stated limits — country of listing, no hedging).
             * @default []
             */
            currencies: components["schemas"]["AllocationSlice"][];
            /**
             * Matrix
             * @description Asset class x region
             * @default []
             */
            matrix: components["schemas"]["MatrixCell"][];
            /**
             * Notes
             * @description Why an axis is missing, when it is — so an empty chart never passes for 'you own nothing there'.
             * @default []
             */
            notes: string[];
            /** Overlap */
            overlap: components["schemas"]["OverlapItem"][];
            /** Rows */
            rows: components["schemas"]["CompositionRow"][];
            /** Sectors */
            sectors: components["schemas"]["AllocationSlice"][];
            /**
             * Total Value
             * @description What the looked-through portfolio is worth — the denominator the weights are shares of. Market where the market can price a position, its last observed value where it cannot.
             */
            total_value: number;
            /**
             * Unconverted
             * @description The codes the weighed investments hold as written, because no rate converts them, with their share under "total_value": every weight is a share of a total that holds them (brief BA).
             */
            unconverted: components["schemas"]["UnconvertedCode"][];
            /**
             * Undecomposed Pct
             * @description The share no source could decompose. Kept explicit so a chart can show it as its own slice instead of quietly normalising it away.
             * @default 0
             */
            undecomposed_pct: number;
        };
        /**
         * PortfolioRow
         * @description One investment position in the portfolio view, with its TWO readings
         *     kept apart: `book_value` is what the position cost, `observed_value` is
         *     what it is worth. They differ whenever a purchase price was recorded, and
         *     answering a question about worth with the cost is the defect this pair
         *     exists to end.
         *
         *     `market_value`/`delta` are filled only for quantity-based, symboled
         *     positions with a market price (live or cached); `as_of` is the close date
         *     that price refers to. An unpriced row still has an `observed_value` — the
         *     figure its last photograph recorded — and that is what it contributes to
         *     `total_market`.
         */
        PortfolioRow: {
            /**
             * As Of
             * @description Market close date the price refers to
             */
            as_of: string | null;
            /** Asset Class */
            asset_class: string | null;
            /** Asset Name */
            asset_name: string;
            /**
             * Avg Cost
             * @description book_value / quantity (average-cost accounting): a price paid only where cost_known; otherwise, in part or whole, a situation's price
             */
            avg_cost: number | null;
            /**
             * Book Paid
             * @description Of book_value, the money PAID, in the base currency: a buy's cash, or a cost recorded on the situation. The rest of the book is a situation's value that no purchase price was recorded for. Equal to book_value when cost_known.
             */
            book_paid: number;
            /**
             * Book Value
             * @description What this position COST, in the base currency: the purchase price recorded on its situation, with or without units, and the buys since; where no price was recorded, the value its photograph was taken at, which is not a cost. `book_paid` says how much of it is money paid, and cost_known is True only when all of it is. The base the P/L is measured against; never an answer to 'what is it worth'.
             */
            book_value: number;
            /**
             * Closed On
             * @description Set when a `close` disposed of this position: it is shown so the exit is visible, rather than the row simply ceasing to exist.
             */
            closed_on: string | null;
            /**
             * Cost Estimated
             * @description True when some of the PAID part was not read off a contract note: a plan's buy priced at a market close, or a recorded cost DERIVED (e.g. from a broker's reported % return). A real number, but not a verified one, and the reader is entitled to know which.
             * @default false
             */
            cost_estimated: boolean;
            /**
             * Cost Known
             * @description True when ALL of the book is money paid. False when some or all of it is a snapshot's value with no recorded purchase: `book_paid` says how much was paid, and only the P/L on the units paid for (`delta_paid`) is a gain; the rest measures movement since the value was written down.
             * @default false
             */
            cost_known: boolean;
            /**
             * Currency
             * @description Listing currency of the live price; null while it is not known, and then the row has no market value — a price in an unknown currency is not converted as if it were the base
             */
            currency: string | null;
            /**
             * Currency Note
             * @description Set when the hand-typed currency disagrees with the listing's own
             */
            currency_note: string | null;
            /**
             * Delta
             * @description market_value − book_value: what the market says today against what was paid. NULL when no quote priced the row — a photograph's own figure is not a price the market made, and putting the difference here would present a month-old statement as performance in the column that means 'a live market versus what you paid' on every other row. The movement is still visible: it is observed_value − book_value, from two named facts.
             */
            delta: number | null;
            /**
             * Delta Paid
             * @description The part of `delta` on the units paid for: their share of market_value less book_paid, a gain or a loss against a price paid. `delta` less this is movement since a situation, not a profit. Equal to delta when cost_known, 0.0 when nothing was paid, null when delta is.
             */
            delta_paid: number | null;
            /**
             * Delta Pct
             * @description delta / book_value — a return measured against cost
             */
            delta_pct: number | null;
            /** Distribution Policy */
            distribution_policy: string | null;
            /**
             * Dividends
             * @description Dividends collected since the snapshot anchor
             */
            dividends: number;
            /**
             * Dividends Estimated
             * @description The part of `dividends` still carrying the market's GROSS figure. An auto-recorded dividend is the declared amount per share, from which no withholding has been taken; correcting the row with the broker's real credit replaces it with the net figure and clears `estimated` in the same gesture. There is no gross/net column, so this is the only thing separating the rows a withholding estimate may be applied to from the rows where applying one would tax the same money twice.
             */
            dividends_estimated: number;
            /**
             * Institution
             * @description The institution holding this position, or null when it is held at none. Null is a real answer, not a missing name: a PAC target that names no institution creates positions like this, and they can never be photographed by a situation or reconciled against one. It used to arrive as the string '?', which a bank actually called that is indistinguishable from.
             */
            institution: string | null;
            /**
             * Institution Id
             * @description The id of the institution holding this position, for a caller that already has one and should not have to match on a name.
             */
            institution_id: number | null;
            /**
             * Last Dividend
             * @description The latest ex-date Yahoo lists for this ticker, from the dividend answers the catch-up keeps; null when it was never asked about or lists none. What the row says when no policy is stated and the ticker's own history decides its dividends.
             */
            last_dividend: string | null;
            /** Live Price */
            live_price: number | null;
            /**
             * Market Value
             * @description In the base currency (converted at the ECB reference rate, or Yahoo's for a currency the ECB does not publish)
             */
            market_value: number | null;
            /**
             * Observed On
             * @description The date this position was last CONFIRMED — the photo it sits in, or its most recent ledger entry. Two different things age: on a priced row the value is today's and only 'I hold N units' is this old; on an unpriced one, everything is. Callers must say which, not just 'stale'.
             */
            observed_on: string | null;
            /**
             * Observed Value
             * @description What this position was last OBSERVED to be worth: the figure its photograph recorded, carried forward through the ledger. Equal to book_value whenever the projection has only one figure to work from: no purchase price was recorded, or no value was (a quantity typed with no price is not an observation of zero), or the position was born in the ledger and no photograph ever saw it.
             */
            observed_value: number;
            /** Quantity */
            quantity: number | null;
            /** Quantity Age Days */
            quantity_age_days: number | null;
            /**
             * Realized Movement
             * @description What they realized on a situation's value that no purchase price was recorded for: the movement since that situation, not a profit. realized_pl plus this is the whole result at average cost.
             */
            realized_movement: number;
            /**
             * Realized Pl
             * @description What sells and closes since the snapshot anchor realized on the units PAID for: a gain or a loss against a price paid
             */
            realized_pl: number;
            /** Symbol */
            symbol: string | null;
            /**
             * Units Paid
             * @description Of quantity, the units that money paid for: a buy's own, and a situation's whose cost is recorded. Null on a row with no units.
             */
            units_paid: number | null;
        };
        /**
         * PrefilledSnapshotRead
         * @description A snapshot started from the previous one, plus what the app did to it.
         *
         *     `needs_attention` is the point of the whole endpoint: it names the rows
         *     nothing could re-price, which are the only ones actually asking for the
         *     user. Everything else was carried over and valued at the new date.
         */
        PrefilledSnapshotRead: {
            /**
             * Base Currency
             * @description The currency this payload's computed amounts are in — the database's base, as the figures were converted. Figures a row states itself (an anchor, a transaction, a valuation) keep their own `currency`.
             */
            base_currency: string;
            /**
             * Copied From
             * @description Date of the situation it started from
             */
            copied_from: string;
            /** Created At */
            created_at: string;
            /**
             * Date
             * Format: date
             * @description Situation date (YYYY-MM-DD)
             */
            date: string;
            /** Id */
            id: number;
            /** Institution Id */
            institution_id: number;
            /**
             * Needs Attention
             * @description Rows carried over unchanged because nothing can price them
             */
            needs_attention: string[];
            /**
             * Not A Code
             * @description Copied rows whose currency is not a currency code. It is copied as written, since only the reader knows what it meant, and said, so the new situation does not carry it forward in silence (brief BA).
             */
            not_a_code: components["schemas"]["NotACode"][];
            /**
             * Note
             * @description Free-form notes
             */
            note: string | null;
            /**
             * Paid Not Kept
             * @description Of those rows, the ones partly bought since the situation it started from whose paid part the new one could not keep, with the units it had paid for: nothing priced them on that day (brief AV).
             */
            paid_not_kept: components["schemas"]["PaidNotKept"][];
            /**
             * Repriced
             * @description Tickers valued at the new date
             */
            repriced: string[];
            /**
             * Unconverted
             * @description The codes `value_base` holds as written, because no rate converts them, with their share of it under "value_base" (brief BA).
             */
            unconverted: components["schemas"]["UnconvertedCode"][];
            /**
             * Value Base
             * @description What this situation was worth, in `base_currency`: its holdings converted at the ECB rate (Yahoo's for a currency the ECB does not publish), by the listing currency where the ticker has one. Computed by the router, never by the model.
             */
            value_base: number;
        };
        /**
         * PriceQuote
         * @description A market price for a symbol (the latest available close).
         *
         *     `name` is what the ticker actually resolved to. It is the check that
         *     catches a ticker pointing at the wrong fund — a plausible price never
         *     does, because the wrong fund has one too.
         */
        PriceQuote: {
            /**
             * As Of
             * Format: date
             */
            as_of: string;
            /** Currency */
            currency: string | null;
            /** Name */
            name: string | null;
            /** Price */
            price: number;
            /** Symbol */
            symbol: string;
        };
        /**
         * QuotableInstrument
         * @description A candidate from the live lookup — a share, ETF, coin or futures
         *     contract, i.e. everything the fund catalogue does not hold.
         *
         *     `price` NEVER travels without `exchange`, and for a measured reason: the
         *     lookup does not return a currency, so the same company on two exchanges
         *     comes back as two bare numbers in different money — one in dollars on NMS
         *     and one in euros on FRA, apart by the exchange rate and the same value. The
         *     currency arrives from a real quote once something is chosen.
         */
        QuotableInstrument: {
            /** Exchange */
            exchange: string | null;
            /** Name */
            name: string | null;
            /** Price */
            price: number | null;
            /**
             * Quote Type
             * @description equity | etf | cryptocurrency | future | index
             */
            quote_type: string | null;
            /** Symbol */
            symbol: string;
        };
        /**
         * RealAssetCreate
         * @description Payload to create a real asset.
         */
        RealAssetCreate: {
            /**
             * Acquisition Date
             * @description Acquisition date (YYYY-MM-DD)
             */
            acquisition_date?: string | null;
            /**
             * Acquisition Value
             * @description Value at acquisition time
             */
            acquisition_value?: number | null;
            /**
             * Category
             * @description Asset category
             */
            category?: string | null;
            /**
             * Currency
             * @description Currency, e.g. EUR
             */
            currency: string;
            /**
             * Name
             * @description Asset name (e.g. 'Milan flat', 'Tesla Model 3')
             */
            name: string;
            /**
             * Notes
             * @description Free-form notes
             */
            notes?: string | null;
        };
        /**
         * RealAssetRead
         * @description Representation of a real asset returned by the API.
         */
        RealAssetRead: {
            /**
             * Acquisition Date
             * @description Acquisition date (YYYY-MM-DD)
             */
            acquisition_date: string | null;
            /**
             * Acquisition Value
             * @description Value at acquisition time
             */
            acquisition_value: number | null;
            /**
             * Category
             * @description Asset category
             */
            category: string | null;
            /** Created At */
            created_at: string;
            /**
             * Currency
             * @description Currency, e.g. EUR
             */
            currency: string;
            /** Id */
            id: number;
            /**
             * Name
             * @description Asset name (e.g. 'Milan flat', 'Tesla Model 3')
             */
            name: string;
            /**
             * Notes
             * @description Free-form notes
             */
            notes: string | null;
        };
        /**
         * RealAssetValuationCreate
         * @description Payload to create a valuation. real_asset_id comes from the URL.
         */
        RealAssetValuationCreate: {
            /**
             * Date
             * Format: date
             * @description Valuation date (YYYY-MM-DD)
             */
            date: string;
            /**
             * Note
             * @description Free-form notes
             */
            note?: string | null;
            /**
             * Value
             * @description Asset value at that date
             */
            value: number;
        };
        /**
         * RealAssetValuationRead
         * @description Representation of a valuation returned by the API.
         */
        RealAssetValuationRead: {
            /** Created At */
            created_at: string;
            /**
             * Date
             * Format: date
             * @description Valuation date (YYYY-MM-DD)
             */
            date: string;
            /** Id */
            id: number;
            /**
             * Note
             * @description Free-form notes
             */
            note: string | null;
            /** Real Asset Id */
            real_asset_id: number;
            /**
             * Value
             * @description Asset value at that date
             */
            value: number;
        };
        /**
         * RealCategorySlice
         * @description One slice of the real allocation (by asset category).
         */
        RealCategorySlice: {
            /** Category */
            category: string;
            /** Value */
            value: number;
        };
        /**
         * RequiredReturnRequest
         * @description Inputs to compute the annual return needed to reach a target.
         */
        RequiredReturnRequest: {
            /**
             * Current Amount
             * @default 0
             */
            current_amount?: number;
            /**
             * Monthly Contribution
             * @default 0
             */
            monthly_contribution?: number;
            /** Target Amount */
            target_amount: number;
            /**
             * Target Date
             * Format: date
             */
            target_date: string;
        };
        /**
         * RequiredReturnResult
         * @description The computed required return (fraction; None if unreachable) + a note.
         */
        RequiredReturnResult: {
            /** Assessment */
            assessment: string;
            /** Required Annual Return */
            required_annual_return: number | null;
            /** Years */
            years: number;
        };
        /**
         * SnapshotCreate
         * @description Payload to create a snapshot. institution_id comes from the URL.
         *
         *     No currency: a situation has none of its own. Each holding states the
         *     currency it is in, and what the situation is worth is theirs converted.
         */
        SnapshotCreate: {
            /**
             * Date
             * Format: date
             * @description Situation date (YYYY-MM-DD)
             */
            date: string;
            /**
             * Note
             * @description Free-form notes
             */
            note?: string | null;
        };
        /**
         * SnapshotRead
         * @description Representation of a snapshot, and what it was worth.
         *
         *     The figure is named for its currency because it used to be named `value`
         *     and was a raw sum of whatever each holding happened to be denominated in.
         *     A name that says nothing about its unit is how a total in lira reached a
         *     screen with a euro sign on it, so the unit is declared beside it.
         */
        SnapshotRead: {
            /**
             * Base Currency
             * @description The currency this payload's computed amounts are in — the database's base, as the figures were converted. Figures a row states itself (an anchor, a transaction, a valuation) keep their own `currency`.
             */
            base_currency: string;
            /** Created At */
            created_at: string;
            /**
             * Date
             * Format: date
             * @description Situation date (YYYY-MM-DD)
             */
            date: string;
            /** Id */
            id: number;
            /** Institution Id */
            institution_id: number;
            /**
             * Note
             * @description Free-form notes
             */
            note: string | null;
            /**
             * Unconverted
             * @description The codes `value_base` holds as written, because no rate converts them, with their share of it under "value_base" (brief BA).
             */
            unconverted: components["schemas"]["UnconvertedCode"][];
            /**
             * Value Base
             * @description What this situation was worth, in `base_currency`: its holdings converted at the ECB rate (Yahoo's for a currency the ECB does not publish), by the listing currency where the ticker has one. Computed by the router, never by the model.
             */
            value_base: number;
        };
        /**
         * SurveyAnswer
         * @description One questionnaire answer (financial-literacy intro or qualitative profile).
         */
        SurveyAnswer: {
            /** Answer */
            answer?: string | null;
            /** Question */
            question?: string | null;
            /** Question Key */
            question_key: string;
            /** Topic */
            topic?: string | null;
        };
        /**
         * SurveyAnswerRead
         * @description A stored survey answer as returned by the API.
         */
        SurveyAnswerRead: {
            /** Answer */
            answer: string | null;
            /** Created At */
            created_at: string;
            /** Id */
            id: number;
            /** Question */
            question: string | null;
            /** Question Key */
            question_key: string;
            /** Topic */
            topic: string | null;
        };
        /**
         * SurveyQuestion
         * @description One question of the Profile form: what it asks, and the kind of answer
         *     it takes. The form draws itself from these (`app/questionnaire.py`), and
         *     the chat's `update_profile` is checked against them.
         *
         *     `type` is how it is answered: "boolean" by yes or no ("unsure" too when
         *     `unsure`), "single" by one of `options`, "number" by digits, "text" and
         *     "longtext" by any words.
         */
        SurveyQuestion: {
            explain_when: components["schemas"]["SurveyQuestionNote"] | null;
            /** Key */
            key: string;
            /** Options */
            options: string[];
            show_if: components["schemas"]["SurveyQuestionCondition"] | null;
            /** Text */
            text: string;
            /** Topic */
            topic: string;
            /**
             * Type
             * @enum {string}
             */
            type: "boolean" | "single" | "text" | "longtext" | "number";
            /**
             * Unsure
             * @default false
             */
            unsure: boolean;
        };
        /**
         * SurveyQuestionCondition
         * @description Show a question only while another question's answer is `equals`.
         */
        SurveyQuestionCondition: {
            /** Equals */
            equals: string;
            /** Key */
            key: string;
        };
        /**
         * SurveyQuestionNote
         * @description A few words shown under a question while its answer is `equals`.
         */
        SurveyQuestionNote: {
            /** Equals */
            equals: string;
            /** Text */
            text: string;
        };
        /**
         * SymbolLookup
         * @description The live lane. Empty when nothing matched OR the source was unreachable —
         *     `reachable` tells the caller which, so an outage is never presented as
         *     'this instrument does not exist'.
         */
        SymbolLookup: {
            /**
             * Reachable
             * @default true
             */
            reachable: boolean;
            /** Results */
            results: components["schemas"]["QuotableInstrument"][];
        };
        /**
         * TaxCountryDefault
         * @description One row of the shipped default table, offered to the reader as a
         *     starting point and never applied behind their back.
         */
        TaxCountryDefault: {
            /** Capital Gains Rate */
            capital_gains_rate: number;
            /** Country */
            country: string;
            /** Dividend Withholding Rate */
            dividend_withholding_rate: number;
            /**
             * Omits
             * @description The carve-outs this flat rate knowingly flattens. Shipped WITH the number because it is what makes a three-country table honest rather than merely short.
             */
            omits: string;
            /**
             * Regime
             * @description The named regime the rate comes from
             */
            regime: string;
        };
        /**
         * TaxEstimate
         * @description A declared tax estimate, never a tax calculation — see app/tax.py for
         *     what is deliberately not being built here.
         *
         *     It rides on the portfolio payload because the two figures it is derived
         *     from are computed there, and a number that travels apart from its base
         *     drifts from it. It is in NO total on that payload: not the book value, not
         *     the market value, not the net worth. Beside them, labelled, carrying the
         *     rate it used — which is what separates an aid to deciding from something
         *     impersonating a return.
         *
         *     Every field may be null, and null means the reader has not said, which this
         *     app treats as a different claim from zero.
         */
        TaxEstimate: {
            /**
             * Capital Gains Rate
             * @description PERCENT, not a fraction. Null when the reader has not set it.
             */
            capital_gains_rate: number | null;
            /**
             * Capital Gains Tax
             * @description taxable_gain x the rate. Null when no rate is set.
             */
            capital_gains_tax: number | null;
            /**
             * Caveats
             * @description Why this figure is approximate, in words, generated beside the number. The page, the advisor and any outside assistant read the same list — a caveat kept only in the UI is one the chat would confidently omit.
             */
            caveats: string[];
            /**
             * Configured
             * @description Whether either rate is set at all. False is the state where the screen must say nobody has answered rather than show a zero — the bases below are still real and still worth reading.
             */
            configured: boolean;
            /**
             * Country
             * @description What the reader called their tax country. A LABEL on the estimate and the seed for the pre-filled rates — nothing downstream branches on it, so a country with no shipped default is not a lesser case.
             */
            country: string | null;
            /**
             * Dividend Withholding
             * @description dividends_gross_estimated x the rate. Null when no rate is set.
             */
            dividend_withholding: number | null;
            /**
             * Dividend Withholding Rate
             * @description PERCENT, not a fraction. Null when the reader has not set it.
             */
            dividend_withholding_rate: number | null;
            /**
             * Dividends Gross Estimated
             * @description The dividend base: ONLY the rows still marked estimated, which are the only ones still carrying a gross figure.
             */
            dividends_gross_estimated: number;
            /**
             * Dividends Recorded Net
             * @description The dividends the reader corrected by hand, which are already net of whatever their broker withheld. Named rather than omitted, because 'no rate was applied here' is a fact about the estimate.
             */
            dividends_recorded_net: number;
            /**
             * Missing Rates
             * @description Which rates a non-empty base is waiting on, so the screen can ask for exactly those.
             */
            missing_rates: string[];
            /**
             * Realized Gain
             * @description The ledger's realized result on the units PAID for, as-is, which may be NEGATIVE. Kept signed and separate from `taxable_gain` so a loss is visible as a loss instead of disappearing into a zero tax.
             */
            realized_gain: number;
            /**
             * Realized Movement
             * @description What sells and closes realized on situations' values that no purchase price was recorded for: a movement, not a gain. No rate is applied to it and `total` leaves its tax out, so every reader of the total says this beside it.
             */
            realized_movement: number;
            /**
             * Regime
             * @description The named regime behind a shipped default (e.g. 'Abgeltungsteuer 25% + 5.5% Solidaritätszuschlag'), so the reader can check the number against something. Null for a country this app ships no default for, including when the rates are set by hand.
             */
            regime: string | null;
            /**
             * Taxable Gain
             * @description max(realized_gain, 0) — the base the rate is applied to. A loss produces no negative tax here: it is not a refund, it is a carry-forward in most regimes, and this tracks neither.
             */
            taxable_gain: number;
            /**
             * Total
             * @description The two halves summed, and NULL whenever a base with something in it has no rate to apply. A total that quietly omitted half of itself would read as 'my tax' while being an understatement.
             */
            total: number | null;
        };
        /**
         * TaxSettings
         * @description The three settings the reader controls, as they are written and read.
         *
         *     Rates are PERCENT (26 means 26%), matching `Liability.interest_rate`, the
         *     one rate this app already stored. Null clears the key.
         */
        TaxSettings: {
            /** Capital Gains Rate */
            capital_gains_rate?: number | null;
            /**
             * Country
             * @description Free text: any country, listed or not
             */
            country?: string | null;
            /** Dividend Withholding Rate */
            dividend_withholding_rate?: number | null;
        };
        /**
         * TaxSettingsRead
         * @description What the reader set, plus the defaults they could choose from.
         *
         *     The known list travels with the current values so the screen has one round
         *     trip and one source of truth for the rates — a table duplicated into the
         *     frontend is a table that goes stale on one side.
         */
        TaxSettingsRead: {
            /** Capital Gains Rate */
            capital_gains_rate: number | null;
            /**
             * Country
             * @description Free text: any country, listed or not
             */
            country: string | null;
            /** Dividend Withholding Rate */
            dividend_withholding_rate: number | null;
            /** Known Countries */
            known_countries: components["schemas"]["TaxCountryDefault"][];
        };
        /**
         * TradingAccountMapping
         * @description Which ledger institution is the trading desk's account (input).
         */
        TradingAccountMapping: {
            /**
             * Institution Id
             * @description The institution the engine trades out of
             */
            institution_id: number;
        };
        /**
         * TradingApprovalResult
         * @description What one POST …/approve produced: the approval row the human's assent
         *     became, the new state row when the registry's guards let it through,
         *     and the fingerprint the confirmation stood on.
         */
        TradingApprovalResult: {
            /** Approval Id */
            approval_id: number;
            /** Evidence */
            evidence: string;
            /** Fingerprint */
            fingerprint: string;
            /** State */
            state: string;
        };
        /**
         * TradingBotDivergence
         * @description One bot's divergence picture: the declared budget, the live feed
         *     counters, the aggregated per-fill evidence, and the distributional
         *     comparison when — and only when — the data volume makes it meaningful.
         */
        TradingBotDivergence: {
            /** Backfilled Bars */
            backfilled_bars: number | null;
            /** Bot */
            bot: string;
            /** Budget Dev Ticks */
            budget_dev_ticks: number | null;
            /** Budget Entry Lag Bars */
            budget_entry_lag_bars: number | null;
            /** Budget Missed Bars */
            budget_missed_bars: number | null;
            distribution: components["schemas"]["TradingDivergenceDistribution"] | null;
            /** Distribution Note */
            distribution_note: string;
            fills: components["schemas"]["TradingDivergenceFillStats"];
            /** Missed Bars */
            missed_bars: number | null;
            /** Open Positions */
            open_positions: components["schemas"]["TradingPosition"][];
        };
        /**
         * TradingBotRails
         * @description One bot's rail state as the desk's snapshot last wrote it — every
         *     number the rails themselves computed, plus the exposure book's slice.
         *     `asof` is the snapshot's write time: the UI says when this was true,
         *     because a rail state without a clock is a rumor.
         */
        TradingBotRails: {
            /** Asof */
            asof: string | null;
            /** Bot */
            bot: string;
            /** Cooldown Remaining S */
            cooldown_remaining_s: number;
            /** Daily Breached */
            daily_breached: boolean;
            /** Daily Loss */
            daily_loss: number;
            /** Daily Loss Consumed */
            daily_loss_consumed: number;
            /** Daily Loss Limit */
            daily_loss_limit: number;
            divergence?: components["schemas"]["TradingRailDivergence"] | null;
            /** Drawdown Pct */
            drawdown_pct: number;
            /** Equity */
            equity: number;
            exposure: components["schemas"]["TradingRailExposure"] | null;
            /** Kill Tripped */
            kill_tripped: boolean;
            /** Killswitch Dd Pct */
            killswitch_dd_pct: number;
            /** Loss Streak */
            loss_streak: number;
            /** Max Losses */
            max_losses: number;
            /** Peak Equity */
            peak_equity: number;
            /** Vetoes Total */
            vetoes_total: number;
        };
        /**
         * TradingClosedTrade
         * @description One settled round-trip the desk wrote — the recent evidence strip.
         */
        TradingClosedTrade: {
            /** Bot */
            bot: string;
            /** Confidence */
            confidence: number;
            /** Entry Dev Ticks */
            entry_dev_ticks: number | null;
            /** Entry Lag Bars */
            entry_lag_bars: number | null;
            /** Entry Price */
            entry_price: number;
            /**
             * Entry Time
             * Format: date-time
             */
            entry_time: string;
            /** Exit Dev Ticks */
            exit_dev_ticks: number | null;
            /** Exit Price */
            exit_price: number;
            /**
             * Exit Time
             * Format: date-time
             */
            exit_time: string;
            /** Fees */
            fees: number;
            /** Gate Source */
            gate_source: string;
            /** Id */
            id: number;
            /** Mode */
            mode: string;
            /** Pnl */
            pnl: number;
            /** Qty */
            qty: number;
            /** Side */
            side: string;
            /**
             * Signal Chain
             * @default {}
             */
            signal_chain?: {
                [key: string]: unknown;
            };
            /** Signal Time */
            signal_time?: string | null;
            /** Symbol */
            symbol: string;
        };
        /**
         * TradingDivergenceDistribution
         * @description Paper-vs-backtest per-trade pnl positioning — present ONLY when both
         *     sides have ≥30 trades (the same statistical bar the validation gate
         *     sets). Descriptive, never inferential: no p-values over small
         *     autocorrelated samples.
         */
        TradingDivergenceDistribution: {
            /** Bt Mean Pnl */
            bt_mean_pnl: number;
            /** Bt Median Pnl */
            bt_median_pnl: number;
            /** Bt P5 */
            bt_p5: number;
            /** Bt P95 */
            bt_p95: number;
            /** Bt Trades */
            bt_trades: number;
            /** Paper Mean Pnl */
            paper_mean_pnl: number;
            /** Paper Mean Within Bt P5 P95 */
            paper_mean_within_bt_p5_p95: boolean;
            /** Paper Trades */
            paper_trades: number;
        };
        /**
         * TradingDivergenceFillStats
         * @description Per-fill drift evidence aggregated over the bot's closed trades —
         *     the mechanical divergence measurement, meaningful at n=1 because each
         *     fill is one kernel fact compared against its own bar.
         */
        TradingDivergenceFillStats: {
            /** Breaches */
            breaches: number;
            /** Max Abs Dev Ticks */
            max_abs_dev_ticks: number | null;
            /** Max Entry Lag Bars */
            max_entry_lag_bars: number | null;
            /** Mean Abs Dev Ticks */
            mean_abs_dev_ticks: number | null;
            /** Measured Fills */
            measured_fills: number;
        };
        /**
         * TradingDivergenceStatus
         * @description /api/trading/divergence — the slice-5 surface. Bots come from two
         *     sources unioned: the rail snapshots (live processes) and the trade
         *     rows (evidence). Empty bots is the honest first-class answer.
         */
        TradingDivergenceStatus: {
            /** Bots */
            bots: components["schemas"]["TradingBotDivergence"][];
            /** Breach Events */
            breach_events: components["schemas"]["TradingRiskEvent"][];
        };
        /**
         * TradingEquityFan
         * @description The bootstrap/permutation equity fan: percentile bands and sample
         *     paths over the trade steps of the validation's Monte Carlo. X is a step
         *     index (trade count along the path), not a clock — the fan answers
         *     "where could this path have gone", not "when".
         */
        TradingEquityFan: {
            /** Actual */
            actual: number[];
            /** Band P5 */
            band_p5: number[];
            /** Band P25 */
            band_p25: number[];
            /** Band P50 */
            band_p50: number[];
            /** Band P75 */
            band_p75: number[];
            /** Band P95 */
            band_p95: number[];
            /** Initial Capital */
            initial_capital: number;
            /** Samples */
            samples: number[][];
            /** Steps */
            steps: number[];
        };
        /** TradingEquityPoint */
        TradingEquityPoint: {
            /** Equity */
            equity: number;
            /** T */
            t: string;
        };
        /**
         * TradingModelRegistry
         * @description GET /api/trading/model-registry — every ML model version with its
         *     promotion role and OOS evidence. Empty is the first-class answer: no
         *     retrain cycle has ever written a row.
         */
        TradingModelRegistry: {
            /** Models */
            models: components["schemas"]["TradingModelVersionItem"][];
            /** Psi Note */
            psi_note: string;
        };
        /**
         * TradingModelVersionItem
         * @description One ML model registry row: champion/challenger role, the OOS metrics
         *     the promotion gate measured, and the PSI drift when — and only when —
         *     it is honestly knowable. PSI is computed per retrain cycle and today
         *     travels inside the supervisor insight's text, never a column: null here
         *     is the documented answer, and the registry panel says where it lives.
         */
        TradingModelVersionItem: {
            /** Id */
            id: number;
            /** Is Champion */
            is_champion: boolean;
            /** Name */
            name: string;
            /** Notes */
            notes: string;
            /** Oos Accuracy */
            oos_accuracy: number;
            /** Oos Precision Long */
            oos_precision_long: number;
            /** Psi Drift */
            psi_drift: number | null;
            /** Role */
            role: string;
            /** Train Window Days */
            train_window_days: number;
            /** Trained At */
            trained_at: string | null;
            /** Version */
            version: number;
        };
        /**
         * TradingPosition
         * @description One open position, exactly what the OpenPosition row carries.
         *
         *     age_seconds is server-computed at read time so the UI never re-derives
         *     age from clock-synchronized arithmetic — one measurement, one clock.
         *     signal_time is nullable because rows from before the kernel migration
         *     never carried it (the model's own comment); null is the honest answer.
         *     There is no rearmed state on the wire: rearm is kernel memory, never
         *     persisted — a position a restart re-armed IS the same position.
         */
        TradingPosition: {
            /** Age Seconds */
            age_seconds: number;
            /** Bot */
            bot: string;
            /** Confidence */
            confidence: number;
            /** Entry Dev Ticks */
            entry_dev_ticks: number | null;
            /** Entry Lag Bars */
            entry_lag_bars: number | null;
            /** Entry Price */
            entry_price: number;
            /** Entry Ref Price */
            entry_ref_price: number | null;
            /** Gate Source */
            gate_source: string;
            /** Id */
            id: number;
            /**
             * Opened At
             * Format: date-time
             */
            opened_at: string;
            /** Qty */
            qty: number;
            /** Side */
            side: string;
            /** Signal Time */
            signal_time: string | null;
            /** Stop Loss */
            stop_loss: number;
            /** Symbol */
            symbol: string;
            /** Take Profit */
            take_profit: number;
        };
        /** TradingProvenance */
        TradingProvenance: {
            /** Data End */
            data_end: string;
            /** Data Rows */
            data_rows: number;
            /** Data Source */
            data_source: string;
            /** Data Start */
            data_start: string;
            /** Seed */
            seed: number;
        };
        /**
         * TradingRailDivergence
         * @description The divergence budget as the version declared it, plus the feed
         *     counters the live process measures against it. None on the wire means
         *     the snapshot predates slice 5 — never zeros, because zero is a claim.
         */
        TradingRailDivergence: {
            /** Backfilled Bars */
            backfilled_bars: number;
            /** Budget Dev Ticks */
            budget_dev_ticks: number;
            /** Budget Entry Lag Bars */
            budget_entry_lag_bars: number;
            /** Budget Missed Bars */
            budget_missed_bars: number;
            /** Missed Bars */
            missed_bars: number;
        };
        /** TradingRailExposure */
        TradingRailExposure: {
            /** Gross Cap */
            gross_cap: number;
            /** Gross Notional */
            gross_notional: number;
            /** Instrument Notional */
            instrument_notional: number;
            /** Symbol Cap */
            symbol_cap: number;
        };
        /**
         * TradingRailsStatus
         * @description The desk's rail state at a glance. `bots` empty is the honest answer
         *     for an engine that never ran — and for the M3 end state of a registry
         *     with zero validated strategies: rails exist, nothing trades beneath
         *     them, and the strip says so.
         */
        TradingRailsStatus: {
            /** Bots */
            bots: components["schemas"]["TradingBotRails"][];
            /** Halt Sentinel */
            halt_sentinel: boolean;
            /** Halt Sentinel Path */
            halt_sentinel_path: string;
            /** Manual Killswitch */
            manual_killswitch: boolean;
            /** Manual Killswitch Note */
            manual_killswitch_note: string;
            /** Recent Events */
            recent_events: components["schemas"]["TradingRiskEvent"][];
            /** Vetoes Today */
            vetoes_today: components["schemas"]["TradingRiskEvent"][];
        };
        /**
         * TradingRegistry
         * @description GET /api/trading/registry — every registered version. Empty is the
         *     first-class answer: with zero validated strategies the lifecycle owns
         *     nothing, and the registry that shows nothing is the gate working.
         */
        TradingRegistry: {
            /** Versions */
            versions: components["schemas"]["TradingRegistryVersion"][];
        };
        /**
         * TradingRegistryVersion
         * @description One strategy version with its lifecycle state, the evidence chain
         *     behind it, the paper track record, and the staleness fingerprint the
         *     approval flow consumes. `fingerprint` digests the inputs the approval
         *     card displays; a card confirmed after they moved answers 409.
         */
        TradingRegistryVersion: {
            /** Code Hash */
            code_hash: string;
            /** Fingerprint */
            fingerprint: string;
            /** Name */
            name: string;
            /** Params */
            params: {
                [key: string]: unknown;
            };
            /** Pending Transition */
            pending_transition: string | null;
            /** State */
            state: string;
            /** State Evidence */
            state_evidence: string;
            /** State Since */
            state_since: string | null;
            /** Strategy Key */
            strategy_key: string;
            /** Timeframe */
            timeframe: string;
            track_record: components["schemas"]["TradingTrackRecord"];
            /** Universe */
            universe: string[];
            /** Validation Id */
            validation_id: number | null;
            /** Version */
            version: number;
            /** Version Id */
            version_id: number;
        };
        /** TradingRiskEvent */
        TradingRiskEvent: {
            /** Bot */
            bot: string;
            /** Created At */
            created_at: string | null;
            /** Decision */
            decision: string;
            /** Id */
            id: number;
            /** Inputs */
            inputs: {
                [key: string]: unknown;
            };
            /** Rail */
            rail: string;
            /** Symbol */
            symbol: string;
        };
        /** TradingRunDetail */
        TradingRunDetail: {
            /** Bot */
            bot: string;
            /** Created At */
            created_at: string | null;
            /** Engine Version */
            engine_version: string | null;
            /** Equity Curve */
            equity_curve: components["schemas"]["TradingEquityPoint"][] | null;
            equity_fan?: components["schemas"]["TradingEquityFan"] | null;
            /** Id */
            id: number;
            metrics: components["schemas"]["TradingRunMetrics"];
            /** Min Trades Required */
            min_trades_required: number | null;
            /** Params */
            params: {
                [key: string]: unknown;
            };
            /** Prob Positive */
            prob_positive: number | null;
            provenance: components["schemas"]["TradingProvenance"] | null;
            /** Reasons */
            reasons: string[];
            /** Sharpe Actual */
            sharpe_actual: number | null;
            /** Started At */
            started_at: string | null;
            /** Symbol */
            symbol: string;
            /** Timeframe */
            timeframe: string;
            /** Trades */
            trades: components["schemas"]["TradingTradeEvidence"][] | null;
            /** Trades Count */
            trades_count: number;
            validation: components["schemas"]["TradingValidationSummary"] | null;
            /** Verdict */
            verdict: string | null;
        };
        /** TradingRunItem */
        TradingRunItem: {
            /** Bot */
            bot: string;
            /** Created At */
            created_at: string | null;
            /** Engine Version */
            engine_version: string | null;
            /** Id */
            id: number;
            metrics: components["schemas"]["TradingRunMetrics"];
            /** Started At */
            started_at: string | null;
            /** Symbol */
            symbol: string;
            /** Timeframe */
            timeframe: string;
            /** Trades Count */
            trades_count: number;
            validation: components["schemas"]["TradingValidationSummary"] | null;
            /** Verdict */
            verdict: string | null;
        };
        /** TradingRunMetrics */
        TradingRunMetrics: {
            /** Max Dd Pct */
            max_dd_pct: number;
            /** Profit Factor */
            profit_factor: number;
            /** Sharpe */
            sharpe: number;
            /** Total Return Pct */
            total_return_pct: number;
            /** Win Rate */
            win_rate: number;
        };
        /**
         * TradingSignalItem
         * @description One recorded emission — side, confidence, the signal bar's own time,
         *     and the outcome it met (entered / veto:* / below_confidence / no_atr /
         *     in_position / exited / flat_noop). `details` carries the sizing chain
         *     for entered and vetoed emissions: risk amount, stop distance, raw and
         *     rounded quantity, notional, the caps. Empty dict elsewhere, never
         *     invented numbers.
         */
        TradingSignalItem: {
            /** Bar Time */
            bar_time: string | null;
            /** Bot */
            bot: string;
            /** Confidence */
            confidence: number;
            /** Created At */
            created_at: string | null;
            /** Details */
            details: {
                [key: string]: unknown;
            };
            /** Id */
            id: number;
            /** Outcome */
            outcome: string;
            /** Side */
            side: string;
            /** Symbol */
            symbol: string;
            /** Timeframe */
            timeframe: string;
        };
        /**
         * TradingSignalsToday
         * @description GET /api/trading/signals/today — today's emissions per bot with the
         *     outcome counts. Empty rows is the first-class answer twice over: an
         *     engine that never ran has no emissions, and an engine whose strategies
         *     stayed silent has none either — the two read apart on the engine lamp,
         *     which is exactly why the lamp exists.
         */
        TradingSignalsToday: {
            /** Date */
            date: string;
            /** Signals */
            signals: components["schemas"]["TradingSignalItem"][];
        };
        /** TradingStatus */
        TradingStatus: {
            /** Db Ok */
            db_ok: boolean;
            /**
             * Engine State
             * @enum {string}
             */
            engine_state: "offline" | "running";
            /** Last Tick At */
            last_tick_at: string | null;
            /** Strategies Registered */
            strategies_registered: number;
            /** Validations Total */
            validations_total: number;
        };
        /** TradingStrategy */
        TradingStrategy: {
            /** Description */
            description: string;
            /** Key */
            key: string;
            /** Name */
            name: string;
            /** Registered */
            registered: boolean;
            /** Symbols */
            symbols: string[];
            /** Timeframe */
            timeframe: string;
        };
        /**
         * TradingStrategyPanel
         * @description One bot's per-strategy panel data: the cumulative realized net pnl
         *     curve derived from the desk's own closed trades (never estimated —
         *     equity_points rows are portfolio-wide, so a per-bot equity would be an
         *     allocation fiction), plus the count the panel captions with.
         */
        TradingStrategyPanel: {
            /** Bot */
            bot: string;
            /** Curve */
            curve: components["schemas"]["TradingEquityPoint"][];
            /** Trades Count */
            trades_count: number;
        };
        /**
         * TradingTrackRecord
         * @description The paper track record summary the approval card carries (design §6):
         *     duration, trades, realized pnl — plus the drift counters, the live
         *     evidence of whether paper execution drifts from the contract. Explicit
         *     nulls when nothing has settled yet, never zeros: zero trades is a fact,
         *     zero pnl over zero trades would be a fiction.
         */
        TradingTrackRecord: {
            /** Drift Breaches */
            drift_breaches: number;
            /** Drift Fills Measured */
            drift_fills_measured: number;
            /** First Exit At */
            first_exit_at: string | null;
            /** Last Exit At */
            last_exit_at: string | null;
            /** Realized Pnl */
            realized_pnl: number | null;
            /** Span Days */
            span_days: number | null;
            /** Trades Count */
            trades_count: number;
        };
        /** TradingTradeEvidence */
        TradingTradeEvidence: {
            /** Entry Price */
            entry_price: number;
            /** Entry Time */
            entry_time: string;
            /** Exit Price */
            exit_price: number;
            /** Exit Time */
            exit_time: string;
            /** Pnl */
            pnl: number;
            /** Qty */
            qty: number;
            /** Side */
            side: string;
        };
        /**
         * TradingValidationQueue
         * @description GET /api/trading/validation-queue — versions awaiting the gates and
         *     the gate's failures with their reasons. Both lists empty is the honest
         *     answer for a pipeline with nothing in flight and nothing failed.
         */
        TradingValidationQueue: {
            /** Awaiting */
            awaiting: components["schemas"]["TradingValidationQueueItem"][];
            /** Failures */
            failures: components["schemas"]["TradingValidationQueueItem"][];
        };
        /**
         * TradingValidationQueueItem
         * @description One version waiting at a gate, or a validation verdict with its
         *     reasons. `kind` distinguishes the two sentences: "awaiting" is a version
         *     in research state; "failure" is a validation row whose verdict is not
         *     validated, carrying the gate's own sentences. Awaiting versions carry no
         *     verdict numbers because none exist — explicit nulls, never zeros.
         */
        TradingValidationQueueItem: {
            /** Bot */
            bot: string | null;
            /** Created At */
            created_at: string | null;
            /** Kind */
            kind: string;
            /** Min Trades Required */
            min_trades_required: number | null;
            /** Permutation P */
            permutation_p: number | null;
            /** Reasons */
            reasons: string[];
            /** Strategy Key */
            strategy_key: string | null;
            /** Timeframe */
            timeframe: string | null;
            /** Trades N */
            trades_n: number | null;
            /** Validation Id */
            validation_id: number | null;
            /** Verdict */
            verdict: string | null;
            /** Version */
            version: number | null;
            /** Version Id */
            version_id: number | null;
        };
        /** TradingValidationSummary */
        TradingValidationSummary: {
            /** Permutation P */
            permutation_p: number | null;
            /** Sharpe Ci Hi */
            sharpe_ci_hi: number | null;
            /** Sharpe Ci Lo */
            sharpe_ci_lo: number | null;
            /** Wf Positive Folds */
            wf_positive_folds: number;
            /** Wf Total Folds */
            wf_total_folds: number;
        };
        /**
         * TransactionRead
         * @description A stored transaction as returned by the API.
         */
        TransactionRead: {
            /** Amount */
            amount: number;
            /**
             * Asset Class
             * @description equity | bond | fund_etf | crypto | ...
             */
            asset_class: string | null;
            /**
             * Asset Name
             * @description Instrument name
             */
            asset_name: string;
            /**
             * Cash Institution Id
             * @description Institution whose cash paid (defaults to institution_id)
             */
            cash_institution_id: number | null;
            /** Created At */
            created_at: string;
            /**
             * Currency
             * @description Currency of `amount` and `fees`: the cash that left or reached the account, e.g. EUR
             */
            currency: string;
            /**
             * Currency Note
             * @description Set when `price_currency` disagrees with the currency the listing actually trades in, so the entry is worth opening and correcting.
             */
            currency_note: string | null;
            /**
             * Date
             * Format: date
             * @description Actual execution date
             */
            date: string;
            /**
             * Estimated
             * @description Priced at the market close, not a real broker fill
             */
            estimated: boolean;
            /**
             * Ex Date
             * @description A dividend's ex-date, the day the catch-up finds it by, whatever day the row is dated (the day its money arrived, once corrected). Set by the app, never by a form; null on every other entry.
             */
            ex_date: string | null;
            /**
             * Fees
             * @description Broker fees/commissions, in `currency`
             * @default 0
             */
            fees: number;
            /**
             * Fx As Of
             * @description The day whose rate turned quantity x unit_price into `amount` (`fx_source` says whose), when the app derived it across two currencies. Null when there was nothing to convert, or when the amount is the reader's own figure.
             */
            fx_as_of: string | null;
            /**
             * Fx Source
             * @description Whose rate `fx_as_of` is: the ECB's, or Yahoo's for a currency the ECB does not publish (brief BA). Null when no rate was used.
             */
            fx_source: ("ECB" | "Yahoo") | null;
            /** Id */
            id: number;
            /**
             * Institution Id
             * @description Institution holding the position this entry moves
             */
            institution_id: number | null;
            /**
             * Isin
             * @description Fund ISIN, when known
             */
            isin: string | null;
            /**
             * Kind
             * @description buy | sell | dividend | close
             * @default buy
             */
            kind: string;
            /**
             * Note
             * @description Free-form notes
             */
            note: string | null;
            /** Plan Id */
            plan_id: number | null;
            /** Plan Occurrence */
            plan_occurrence: string | null;
            /**
             * Price Currency
             * @description Currency of `unit_price` — the listing's, e.g. USD. Required for a buy, a sell and a dividend; a close has no price and leaves it empty.
             */
            price_currency: string | null;
            /**
             * Quantity
             * @description Units moved; for a dividend, the units held at the ex-date
             * @default 0
             */
            quantity: number;
            /**
             * Symbol
             * @description Yahoo ticker (e.g. VWCE.MI)
             */
            symbol: string | null;
            /**
             * Unit Price
             * @description Price per unit; for a dividend, the dividend per share
             * @default 0
             */
            unit_price: number;
        };
        /**
         * TransactionWrite
         * @description What a PERSON may post to `/api/transactions` — which is not the same
         *     thing as what the ledger is able to store.
         *
         *     `institution_id` is required here and required nowhere else. A row with
         *     NEITHER institution column set is skipped by the cash register, which keeps
         *     only the entries belonging to the institution it is computing and finds
         *     that `None` equals no id there is; the position the same row creates is
         *     bucketed under `None` and counted in full. One half of the transaction is
         *     addressed to an institution and the other half to nobody, so the money
         *     spent never leaves an account and the purchase adds its own cost to the net
         *     worth. Measured: one institution holding 1000, a buy of 10 units at 10.00
         *     with no institution named, and the net worth went from 1000.00 to 1100.00.
         *
         *     It is the CASH side that makes this required rather than any preference of
         *     the schema's — the money came from somewhere, and with no institution named
         *     the app has nowhere to take it from.
         *
         *     The column stays nullable and `TransactionCreate` stays loose on purpose:
         *     the PAC writes rows with no HOLDING institution (a plan target that names
         *     none) while always naming the PAYING one, and those rows are unreachable
         *     but arithmetically right. Requiring the field of them is a separate
         *     decision. This subclass narrows the one door a reader posts through, and
         *     leaves the internal one alone.
         */
        TransactionWrite: {
            /**
             * Amount
             * @description Actual cash moved, never negative, in `currency`. Defaults to quantity*unit_price + fees for a buy, and quantity*unit_price - fees (net proceeds) for a sell or dividend — with quantity*unit_price converted from `price_currency` at the rates of `date` when the two currencies differ. A close has no units to derive it from, so it must state it — 0 is allowed, silence is not.
             */
            amount?: number | null;
            /**
             * Asset Class
             * @description equity | bond | fund_etf | crypto | ...
             */
            asset_class?: string | null;
            /**
             * Asset Name
             * @description Instrument name
             */
            asset_name: string;
            /**
             * Cash Institution Id
             * @description Institution whose cash paid (defaults to institution_id)
             */
            cash_institution_id?: number | null;
            /**
             * Currency
             * @description Currency of `amount` and `fees`: the cash that left or reached the account, e.g. EUR
             */
            currency: string;
            /**
             * Date
             * Format: date
             * @description Actual execution date
             */
            date: string;
            /**
             * Fees
             * @description Broker fees/commissions, in `currency`
             * @default 0
             */
            fees?: number;
            /**
             * Institution Id
             * @description Where the position is held — and, unless cash_institution_id says otherwise, whose cash moves. Required: an entry naming no institution spends money no account ever loses.
             */
            institution_id: number;
            /**
             * Isin
             * @description Fund ISIN, when known
             */
            isin?: string | null;
            /**
             * Kind
             * @description buy | sell | dividend | close
             * @default buy
             */
            kind?: string;
            /**
             * Note
             * @description Free-form notes
             */
            note?: string | null;
            /**
             * Price Currency
             * @description Currency of `unit_price` — the listing's, e.g. USD. Required for a buy, a sell and a dividend; a close has no price and leaves it empty.
             */
            price_currency?: string | null;
            /**
             * Quantity
             * @description Units moved; for a dividend, the units held at the ex-date
             * @default 0
             */
            quantity?: number;
            /**
             * Symbol
             * @description Yahoo ticker (e.g. VWCE.MI)
             */
            symbol?: string | null;
            /**
             * Unit Price
             * @description Price per unit; for a dividend, the dividend per share
             * @default 0
             */
            unit_price?: number;
        };
        /**
         * TransferCreate
         * @description Payload to create a transfer.
         */
        TransferCreate: {
            /**
             * Amount
             * @description Amount that left the source, in `currency`
             */
            amount: number;
            /**
             * Currency
             * @description Currency of the source side, e.g. EUR
             */
            currency: string;
            /**
             * Date
             * Format: date
             * @description Transfer date (YYYY-MM-DD)
             */
            date: string;
            /**
             * From Institution Id
             * @description Source institution id
             */
            from_institution_id?: number | null;
            /**
             * Note
             * @description Free-form notes
             */
            note?: string | null;
            /**
             * To Amount
             * @description Amount that reached the destination, in `to_currency`, from its statement. Left out, it is `amount` when the two currencies are the same, and otherwise worked out at the rate final for `date`: the ECB's, or Yahoo's for a currency the ECB does not publish.
             */
            to_amount?: number | null;
            /**
             * To Currency
             * @description Currency of the destination side, e.g. EUR
             */
            to_currency: string;
            /**
             * To Institution Id
             * @description Target institution id
             */
            to_institution_id?: number | null;
        };
        /**
         * TransferRead
         * @description A stored transfer as returned by the API.
         */
        TransferRead: {
            /**
             * Amount
             * @description Amount that left the source, in `currency`
             */
            amount: number;
            /** Created At */
            created_at: string;
            /**
             * Currency
             * @description Currency of the source side, e.g. EUR
             */
            currency: string;
            /**
             * Date
             * Format: date
             * @description Transfer date (YYYY-MM-DD)
             */
            date: string;
            /**
             * From Institution Id
             * @description Source institution id
             */
            from_institution_id: number | null;
            /**
             * Fx As Of
             * @description The day whose rate `to_amount` was worked out at (`fx_source` says whose); null when it was stated, or when both sides share a currency
             */
            fx_as_of: string | null;
            /**
             * Fx Source
             * @description Whose rate `fx_as_of` is: the ECB's, or Yahoo's for a currency the ECB does not publish (brief BA). Null when no rate was used.
             */
            fx_source: ("ECB" | "Yahoo") | null;
            /** Id */
            id: number;
            /**
             * Note
             * @description Free-form notes
             */
            note: string | null;
            /** To Amount */
            to_amount: number;
            /**
             * To Currency
             * @description Currency of the destination side, e.g. EUR
             */
            to_currency: string;
            /**
             * To Institution Id
             * @description Target institution id
             */
            to_institution_id: number | null;
        };
        /**
         * UnconvertedCode
         * @description A code that reached this page's figures as written, because no rate
         *     converts it (brief BA, D2 (c)).
         *
         *     The fallback itself is deliberate: an amount no source has priced is kept
         *     rather than dropped, since a total quietly short by a whole account is as
         *     wrong as one quietly inflated (`fx.Converter.to_base_or_as_stored`). What
         *     the page says, in the order the reader acts on it: what kind of code it is,
         *     where it is written, and how much of each figure it is (`notice`).
         */
        UnconvertedCode: {
            /**
             * Currency
             * @description The code as the rows state it ("" for a row that states none)
             */
            currency: string;
            /**
             * More Rows
             * @description How many more rows than those listed
             * @default 0
             */
            more_rows: number;
            /**
             * Not A Code
             * @description True when it is not a currency code at all, a typo corrected on its row; false when it is a currency no source quotes
             */
            not_a_code: boolean;
            /**
             * Rows
             * @description The rows it is written on, newest first
             */
            rows: components["schemas"]["UnconvertedRow"][];
            /**
             * Shares
             * @description How much of each figure of this payload the code is, as written and signed, by the figure's field name: the figure computed again with the code at 0, and the difference. A debt's share is in the debts and leaves the net worth; a monthly flow's is a month's; a figure the code does not move is left out.
             */
            shares: {
                [key: string]: number;
            };
        };
        /**
         * UnconvertedRow
         * @description A row an unconverted code is written on, as the page names it.
         */
        UnconvertedRow: {
            /**
             * Kind
             * @description What the row is: a position, a real asset, a debt, ...
             */
            kind: string;
            /**
             * Name
             * @description Its name, or its account's
             */
            name: string;
            /**
             * Where
             * @description Its account and day, when it has them
             */
            where: string | null;
        };
        /**
         * UnreadPurchases
         * @description Purchases on record that could not be read into a row, because a
         *     situation's units disagreed with the ledger's there: said, with no button,
         *     so they do not leave in silence (brief AW). One per row, the most recent.
         */
        UnreadPurchases: {
            /** Asset Name */
            asset_name: string;
            /** Holding Id */
            holding_id: number;
            /** Institution */
            institution: string | null;
            /** Institution Id */
            institution_id: number;
            /**
             * Opening Paid
             * @description A cost recorded on the situation the reading started from, part of `paid`, in the base currency; null when it started from no cost
             */
            opening_paid: number | null;
            /**
             * Paid
             * @description Not read, in the base currency
             */
            paid: number;
            /**
             * Purchases
             * @description How many purchases are behind it
             */
            purchases: number;
            /** Since */
            since: string;
            /**
             * Situation Date
             * @description The situation that disagreed
             */
            situation_date: string;
            /**
             * Stated Units
             * @description The units it says
             */
            stated_units: number;
            /** Symbol */
            symbol: string;
            /**
             * Units
             * @description The units that money paid for
             */
            units: number;
            /**
             * Walked Units
             * @description The units the ledger gives there
             */
            walked_units: number;
        };
        /** ValidationError */
        ValidationError: {
            /** Context */
            ctx?: Record<string, never>;
            /** Input */
            input?: unknown;
            /** Location */
            loc: (string | number)[];
            /** Message */
            msg: string;
            /** Error Type */
            type: string;
        };
        /**
         * WatchlistItemRead
         * @description A stored watchlist line as the API returns it.
         */
        WatchlistItemRead: {
            /** Added At */
            added_at: string;
            /**
             * Amount Assumptions
             * @description What the amounts assumed, in the chat's words
             */
            amount_assumptions: string | null;
            /**
             * Amount Currency
             * @description The currency of the amounts: the base on the day they were sized
             */
            amount_currency: string | null;
            /**
             * Amount Figures
             * @description What the amounts stood on, in the app's words, with the day they were computed
             */
            amount_figures: string | null;
            /**
             * Amount Monthly
             * @description A sum to put in each month, in amount_currency
             */
            amount_monthly: number | null;
            /**
             * Amount Now
             * @description A sum to put in at once, in amount_currency
             */
            amount_now: number | null;
            /**
             * Based On
             * @description What the reader declared that this rests on
             */
            based_on: string;
            /** Id */
            id: number;
            /**
             * Isin
             * @description A fund's ISIN, from the catalogue: its identity. Null on a share's line, which the symbol identifies
             */
            isin: string | null;
            /**
             * Name
             * @description The instrument's name, as the catalogue or Yahoo writes it
             */
            name: string;
            /**
             * Reason
             * @description Why this was suggested
             */
            reason: string;
            /**
             * Symbol
             * @description On a fund's line, a quotable symbol from the live lookup if one was found, never the catalogue's `base_ticker`, which is not a Yahoo symbol. On a share's line, the identity: the symbol Yahoo lists it under.
             */
            symbol: string | null;
            /**
             * Unknowns
             * @description What the suggestion does NOT know about them
             */
            unknowns: string;
        };
    };
    responses: never;
    parameters: never;
    requestBodies: never;
    headers: never;
    pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
    list_accumulation_plans_api_accumulation_plans_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AccumulationPlanRead"][];
                };
            };
        };
    };
    create_accumulation_plan_api_accumulation_plans_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AccumulationPlanWrite"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AccumulationPlanRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_accumulation_plan_api_accumulation_plans__plan_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                plan_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AccumulationPlanRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    update_accumulation_plan_api_accumulation_plans__plan_id__put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                plan_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AccumulationPlanWrite"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AccumulationPlanRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    delete_accumulation_plan_api_accumulation_plans__plan_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                plan_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_chain_runs_api_advisor_chain_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ChainRunSummary"][];
                };
            };
        };
    };
    get_chain_run_api_advisor_chain__run_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                run_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ChainRunRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_all_cash_anchors_api_cash_anchors_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CashAnchorRead"][];
                };
            };
        };
    };
    get_cash_anchor_api_cash_anchors__anchor_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                anchor_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CashAnchorRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    update_cash_anchor_api_cash_anchors__anchor_id__put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                anchor_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CashAnchorCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CashAnchorRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    delete_cash_anchor_api_cash_anchors__anchor_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                anchor_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    what_deleting_it_moves_api_cash_anchors__anchor_id__deletion_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                anchor_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DeletionRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_cash_positions_api_cash_positions_get: {
        parameters: {
            query?: {
                as_of?: string | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CashPosition"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    send_api_chat_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ChatRequest"];
            };
        };
        responses: {
            /** @description Server-sent events: `start`, then `decided`/`thought`/`delta`/`tool`/`source`/`step`/`card` as they happen, then exactly one `done` or one `error`. */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ChatStart"] | components["schemas"]["ChatThought"] | components["schemas"]["ChatDelta"] | components["schemas"]["ChatTool"] | components["schemas"]["ChatSources"] | components["schemas"]["ChatStep"] | components["schemas"]["ChatCard"] | components["schemas"]["ChatDecided"] | components["schemas"]["ChatDone"] | components["schemas"]["ChatError"];
                    "text/event-stream": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    decide_api_chat_cards__card_id__post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                card_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ChatCardDecision"];
            };
        };
        responses: {
            /** @description Server-sent events: `start`, then `decided`/`thought`/`delta`/`tool`/`source`/`step`/`card` as they happen, then exactly one `done` or one `error`. */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ChatStart"] | components["schemas"]["ChatThought"] | components["schemas"]["ChatDelta"] | components["schemas"]["ChatTool"] | components["schemas"]["ChatSources"] | components["schemas"]["ChatStep"] | components["schemas"]["ChatCard"] | components["schemas"]["ChatDecided"] | components["schemas"]["ChatDone"] | components["schemas"]["ChatError"];
                    "text/event-stream": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_conversations_api_chat_conversations_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ChatConversationRead"][];
                };
            };
        };
    };
    get_conversation_api_chat_conversations__conversation_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                conversation_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ChatConversationDetail"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    delete_conversation_api_chat_conversations__conversation_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                conversation_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_models_api_chat_models_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ChatModelsRead"];
                };
            };
        };
    };
    get_allocation_api_dashboard_allocation_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DashboardAllocation"];
                };
            };
        };
    };
    get_cashflow_api_dashboard_cashflow_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CashFlowSummary"];
                };
            };
        };
    };
    get_net_worth_series_api_dashboard_net_worth_series_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["NetWorthPoint"][];
                };
            };
        };
    };
    get_portfolio_api_dashboard_portfolio_get: {
        parameters: {
            query?: {
                live?: boolean;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Portfolio"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_portfolio_composition_api_dashboard_portfolio_composition_get: {
        parameters: {
            query?: {
                refresh?: boolean;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PortfolioComposition"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_summary_api_dashboard_summary_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DashboardSummary"];
                };
            };
        };
    };
    list_items_api_expenses_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ExpenseRead"][];
                };
            };
        };
    };
    create_item_api_expenses_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ExpenseCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ExpenseRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_item_api_expenses__item_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                item_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ExpenseRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    update_item_api_expenses__item_id__put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                item_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ExpenseCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ExpenseRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    delete_item_api_expenses__item_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                item_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_fx_rates_api_fx_rates_get: {
        parameters: {
            query?: {
                refresh?: boolean;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["FxRateRead"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_goals_api_goals_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GoalRead"][];
                };
            };
        };
    };
    create_goal_api_goals_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["GoalCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GoalRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_goal_api_goals__goal_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                goal_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GoalRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    update_goal_api_goals__goal_id__put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                goal_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["GoalCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GoalRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    delete_goal_api_goals__goal_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                goal_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    health_api_health_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
        };
    };
    get_holding_api_holdings__holding_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                holding_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HoldingRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    update_holding_api_holdings__holding_id__put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                holding_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["HoldingCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HoldingRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    delete_holding_api_holdings__holding_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                holding_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    accept_paid_api_holdings__holding_id__paid_recovery_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                holding_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PaidAccept"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HoldingRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    decline_paid_api_holdings__holding_id__paid_recovery_decline_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                holding_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    refresh_holding_price_api_holdings__holding_id__refresh_price_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                holding_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HoldingRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_items_api_income_sources_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["IncomeSourceRead"][];
                };
            };
        };
    };
    create_item_api_income_sources_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["IncomeSourceCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["IncomeSourceRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_item_api_income_sources__item_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                item_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["IncomeSourceRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    update_item_api_income_sources__item_id__put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                item_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["IncomeSourceCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["IncomeSourceRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    delete_item_api_income_sources__item_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                item_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_institutions_api_institutions_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["InstitutionRead"][];
                };
            };
        };
    };
    create_institution_api_institutions_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["InstitutionCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["InstitutionRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_institution_api_institutions__institution_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                institution_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["InstitutionRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    update_institution_api_institutions__institution_id__put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                institution_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["InstitutionCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["InstitutionRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    delete_institution_api_institutions__institution_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                institution_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_cash_position_api_institutions__institution_id__cash_get: {
        parameters: {
            query?: {
                as_of?: string | null;
            };
            header?: never;
            path: {
                institution_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CashPosition"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_cash_anchors_api_institutions__institution_id__cash_anchors_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                institution_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CashAnchorRead"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_cash_anchor_api_institutions__institution_id__cash_anchors_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                institution_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CashAnchorCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CashAnchorRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_snapshots_api_institutions__institution_id__snapshots_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                institution_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SnapshotRead"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_snapshot_api_institutions__institution_id__snapshots_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                institution_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SnapshotCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SnapshotRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_prefilled_snapshot_api_institutions__institution_id__snapshots_prefilled_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                institution_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SnapshotCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PrefilledSnapshotRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    catalogue_status_api_instruments_catalogue_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CatalogueStatus"];
                };
            };
        };
    };
    ensure_catalogue_api_instruments_catalogue_ensure_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CatalogueStatus"];
                };
            };
        };
    };
    refresh_catalogue_api_instruments_catalogue_refresh_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CatalogueStatus"];
                };
            };
        };
    };
    lookup_symbols_api_instruments_lookup_get: {
        parameters: {
            query?: {
                limit?: number;
                /** @description Free text: company, coin, ticker */
                q?: string;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SymbolLookup"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    search_instruments_api_instruments_search_get: {
        parameters: {
            query?: {
                limit?: number;
                /** @description Free text: name, issuer, ticker */
                q?: string;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["InstrumentSearch"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_liabilities_api_liabilities_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["LiabilityRead"][];
                };
            };
        };
    };
    create_liability_api_liabilities_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["LiabilityCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["LiabilityRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_liability_api_liabilities__liability_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                liability_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["LiabilityRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    update_liability_api_liabilities__liability_id__put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                liability_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["LiabilityCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["LiabilityRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    delete_liability_api_liabilities__liability_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                liability_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_balances_api_liabilities__liability_id__balances_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                liability_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["LiabilityBalanceRead"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_balance_api_liabilities__liability_id__balances_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                liability_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["LiabilityBalanceCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["LiabilityBalanceRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    update_balance_api_liability_balances__balance_id__put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                balance_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["LiabilityBalanceCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["LiabilityBalanceRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    delete_balance_api_liability_balances__balance_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                balance_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_fund_overview_api_overview_fund_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OverviewFund"];
                };
            };
        };
    };
    put_trading_account_api_overview_trading_account_put: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["TradingAccountMapping"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OverviewReconciliation"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    accept_all_paid_api_paid_recovery_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PaidAcceptAll"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HoldingRead"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    required_return_api_planning_required_return_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RequiredReturnRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RequiredReturnResult"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_listing_currencies_api_prices_listing_currencies_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: string;
                    };
                };
            };
        };
    };
    get_quote_api_prices_quote_get: {
        parameters: {
            query: {
                /** @description Close on/just before this date, for recording a past purchase */
                on?: string | null;
                symbol: string;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PriceQuote"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    resolve_isin_api_prices_resolve_get: {
        parameters: {
            query: {
                isin: string;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["IsinSuggestion"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_valuation_api_real_asset_valuations__valuation_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                valuation_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RealAssetValuationRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    update_valuation_api_real_asset_valuations__valuation_id__put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                valuation_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RealAssetValuationCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RealAssetValuationRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    delete_valuation_api_real_asset_valuations__valuation_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                valuation_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_real_assets_api_real_assets_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RealAssetRead"][];
                };
            };
        };
    };
    create_real_asset_api_real_assets_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RealAssetCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RealAssetRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_real_asset_api_real_assets__real_asset_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                real_asset_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RealAssetRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    update_real_asset_api_real_assets__real_asset_id__put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                real_asset_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RealAssetCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RealAssetRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    delete_real_asset_api_real_assets__real_asset_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                real_asset_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_valuations_api_real_assets__real_asset_id__valuations_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                real_asset_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RealAssetValuationRead"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_valuation_api_real_assets__real_asset_id__valuations_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                real_asset_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RealAssetValuationCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RealAssetValuationRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_base_currency_api_settings_base_currency_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BaseCurrencySettingRead"];
                };
            };
        };
    };
    put_base_currency_api_settings_base_currency_put: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["BaseCurrencySetting"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BaseCurrencySettingRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_tax_settings_api_settings_tax_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TaxSettingsRead"];
                };
            };
        };
    };
    put_tax_settings_api_settings_tax_put: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["TaxSettings"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TaxSettingsRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_snapshot_api_snapshots__snapshot_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                snapshot_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SnapshotRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    update_snapshot_api_snapshots__snapshot_id__put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                snapshot_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SnapshotCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SnapshotRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    delete_snapshot_api_snapshots__snapshot_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                snapshot_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_holdings_api_snapshots__snapshot_id__holdings_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                snapshot_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HoldingRead"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_holding_api_snapshots__snapshot_id__holdings_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                snapshot_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["HoldingCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HoldingRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_survey_api_survey_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SurveyAnswerRead"][];
                };
            };
        };
    };
    put_survey_api_survey_put: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SurveyAnswer"][];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SurveyAnswerRead"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_survey_questions_api_survey_questions_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SurveyQuestion"][];
                };
            };
        };
    };
    list_backtest_runs_api_trading_backtest_runs_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TradingRunItem"][];
                };
            };
        };
    };
    backtest_run_detail_api_trading_backtest_runs__run_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                run_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TradingRunDetail"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    trading_divergence_api_trading_divergence_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TradingDivergenceStatus"];
                };
            };
        };
    };
    set_kill_switch_api_trading_kill_switch_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["KillSwitchRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["KillSwitchState"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    model_registry_api_trading_model_registry_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TradingModelRegistry"];
                };
            };
        };
    };
    list_positions_api_trading_positions_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TradingPosition"][];
                };
            };
        };
    };
    list_recent_trades_api_trading_positions_recent_trades_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TradingClosedTrade"][];
                };
            };
        };
    };
    trading_rails_api_trading_rails_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TradingRailsStatus"];
                };
            };
        };
    };
    trading_registry_api_trading_registry_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TradingRegistry"];
                };
            };
        };
    };
    approve_version_api_trading_registry__version_id__approve_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                version_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ApproveRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TradingApprovalResult"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    signals_today_api_trading_signals_today_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TradingSignalsToday"];
                };
            };
        };
    };
    trading_status_api_trading_status_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TradingStatus"];
                };
            };
        };
    };
    trading_strategies_api_trading_strategies_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TradingStrategy"][];
                };
            };
        };
    };
    strategy_panels_api_trading_strategy_panels_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TradingStrategyPanel"][];
                };
            };
        };
    };
    validation_queue_api_trading_validation_queue_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TradingValidationQueue"];
                };
            };
        };
    };
    list_transactions_api_transactions_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TransactionRead"][];
                };
            };
        };
    };
    create_transaction_api_transactions_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["TransactionWrite"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TransactionRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_transaction_api_transactions__tx_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                tx_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TransactionRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    update_transaction_api_transactions__tx_id__put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                tx_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["TransactionWrite"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TransactionRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    delete_transaction_api_transactions__tx_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                tx_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    catch_up_api_transactions_catch_up_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CatchUpResult"];
                };
            };
        };
    };
    answer_dividend_api_transactions_dividend_answer_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["DividendAnswer"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CatchUpResult"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_transfers_api_transfers_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TransferRead"][];
                };
            };
        };
    };
    create_transfer_api_transfers_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["TransferCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TransferRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_transfer_api_transfers__transfer_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                transfer_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TransferRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    update_transfer_api_transfers__transfer_id__put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                transfer_id: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["TransferCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TransferRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    delete_transfer_api_transfers__transfer_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                transfer_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    what_deleting_it_moves_api_transfers__transfer_id__deletion_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                transfer_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DeletionRead"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_watchlist_api_watchlist_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WatchlistItemRead"][];
                };
            };
        };
    };
    delete_watchlist_item_api_watchlist__item_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                item_id: number;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
}
