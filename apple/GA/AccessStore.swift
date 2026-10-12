import Foundation
import Observation
import RevenueCat
import StoreKit

@MainActor
@Observable
final class AccessStore {
    private(set) var products: [AccessOption: AccessProduct] = [:]
    private(set) var statistics: AccessStatistics?
    private(set) var freeGrant: AccessFreeGrant?
    private(set) var paidExpiration: Date?
    private(set) var recoveryCode: String?
    private(set) var isLoading = false
    private(set) var isBusy = false
    var notice: String?
    var errorMessage: String?
    private(set) var manageSubscriptionsURL = URL(string: "https://apps.apple.com/account/subscriptions")!

    @ObservationIgnored private let client = AccessClient()
    @ObservationIgnored private var installation: AccessInstallation?
    @ObservationIgnored private var revenuecatProducts: [AccessOption: StoreProduct] = [:]
    @ObservationIgnored private var storekitProducts: [AccessOption: Product] = [:]
    @ObservationIgnored private var updatesTask: Task<Void, Never>?
    @ObservationIgnored private var expiryTask: Task<Void, Never>?
    @ObservationIgnored private var started = false
    @ObservationIgnored private var pendingRequest: (id: String, message: String)?
    @ObservationIgnored private var retainPurchasesIdentity = false
    @ObservationIgnored private var backendGeneration: UInt64 = 0
    private var evaluatedAt = Date()

    private struct CachedGrant: Codable {
        let grant: AccessFreeGrant
        let verifiedAt: Date
    }
    @ObservationIgnored private var verifiedAt: Date?

    var hasAccess: Bool {
        let now = max(evaluatedAt, Date())
        let paid = paidExpiration.map { now < $0 } ?? false
        // A backwards clock must not resurrect an expired offline grant.
        let clockIsValid = verifiedAt.map { now >= $0.addingTimeInterval(-300) } ?? false
        return paid || (clockIsValid && (freeGrant?.isValid(at: now) ?? false))
    }

    var usesLocalStoreKit: Bool {
        #if DEBUG
        Self.publicSDKKey == nil || ProcessInfo.processInfo.environment["GA_USE_LOCAL_STOREKIT"] == "1"
        #else
        false
        #endif
    }

    init() {
        do { try loadSavedAccess() }
        catch { errorMessage = error.localizedDescription }
    }

    func start() async {
        if started { return }
        started = true
        do { try configurePurchases() }
        catch { errorMessage = error.localizedDescription }
        startUpdates()
        await refresh()
    }

    func refresh() async {
        guard !isLoading, !isBusy else { return }
        isLoading = true
        defer { isLoading = false; evaluatedAt = Date() }
        // Backend availability never determines whether Apple purchases can
        // be restored or whether existing paid entitlements can be refreshed.
        async let backend: Void = refreshBackend()
        async let purchases: Void = refreshPaidAccess()
        _ = await (backend, purchases)
        await refreshStatistics()
    }

    func purchase(_ option: AccessOption) async {
        guard option != .free, !isBusy else { return }
        isBusy = true
        notice = nil
        errorMessage = nil
        defer { isBusy = false; evaluatedAt = Date() }
        // Count the button tap even when the native transaction is cancelled.
        Task { await recordSelection(option) }
        do {
            if usesLocalStoreKit {
                guard let product = storekitProducts[option] else { throw PurchaseError.productUnavailable }
                let result = try await product.purchase()
                switch result {
                case .success(let verification):
                    guard case .verified(let transaction) = verification else { throw PurchaseError.unverified }
                    await updateStoreKitAccess()
                    await transaction.finish()
                    notice = hasAccess ? "Dein App-Zugang ist aktiviert." : "Der Kauf wird noch geprüft. Bitte aktualisiere deinen Zugang."
                case .userCancelled: notice = "Kauf abgebrochen. Du kannst jederzeit erneut wählen."
                case .pending: notice = "Der Kauf wartet auf eine Freigabe. Dein Zugang wird nach der Bestätigung aktiviert."
                @unknown default: throw PurchaseError.unverified
                }
            } else {
                guard Purchases.isConfigured, let product = revenuecatProducts[option] else { throw PurchaseError.productUnavailable }
                let result = try await Purchases.shared.purchase(product: product)
                if result.userCancelled { notice = "Kauf abgebrochen. Du kannst jederzeit erneut wählen." }
                else {
                    apply(result.customerInfo)
                    notice = hasAccess ? "Dein App-Zugang ist aktiviert." : "Der Kauf wird noch geprüft. Bitte aktualisiere deinen Zugang."
                }
            }
            await loadProducts()
        } catch {
            let purchaseError = error as NSError
            if purchaseError.domain == RevenueCat.ErrorCode.errorDomain,
               purchaseError.code == RevenueCat.ErrorCode.purchaseCancelledError.rawValue {
                notice = "Kauf abgebrochen. Du kannst jederzeit erneut wählen."
            } else if purchaseError.domain == RevenueCat.ErrorCode.errorDomain,
                      purchaseError.code == RevenueCat.ErrorCode.paymentPendingError.rawValue {
                notice = "Der Kauf wartet auf eine Freigabe. Dein Zugang wird nach der Bestätigung aktiviert."
            } else { errorMessage = purchaseErrorMessage(error) }
        }
    }

    func restorePurchases() async {
        guard !isBusy else { return }
        isBusy = true
        notice = nil
        errorMessage = nil
        defer { isBusy = false; evaluatedAt = Date() }
        do {
            if usesLocalStoreKit {
                try await AppStore.sync()
                await updateStoreKitAccess()
            } else {
                guard Purchases.isConfigured else { throw PurchaseError.notConfigured }
                apply(try await Purchases.shared.restorePurchases())
            }
            notice = paidExpiration.map { $0 > Date() } == true
                ? "Dein Abo wurde wiederhergestellt."
                : "Es wurde kein aktives Abo gefunden. Für ein kostenloses Jahr nutze deinen Wiederherstellungscode."
            await loadProducts()
        } catch { errorMessage = purchaseErrorMessage(error) }
    }

    @discardableResult
    func submitFreeRequest(_ message: String) async -> Bool {
        guard !isBusy, !isLoading else { return false }
        let trimmed = message.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty, trimmed.count <= 5_000 else {
            errorMessage = "Eine klare Bitte mit höchstens 5.000 Zeichen genügt."
            return false
        }
        isBusy = true
        let generation = beginBackendMutation()
        notice = nil
        errorMessage = nil
        defer { isBusy = false }
        if pendingRequest?.message != trimmed { pendingRequest = (UUID().uuidString, trimmed) }
        do {
            let identity = try await ensureInstallation(generation: generation)
            let grant = try await client.submitFreeRequest(message: trimmed, requestID: pendingRequest!.id, installation: identity)
            try save(grant, for: identity, generation: generation)
            pendingRequest = nil
            notice = grant.isValid() ? "Dein kostenloses Jahr ist freigeschaltet. Es endet ohne Zahlung."
                : "Deine Bitte ist eingegangen. Der Zugang ist noch nicht freigeschaltet."
            return true
        } catch {
            if generation == backendGeneration, !(error is ObsoleteBackendResult) { errorMessage = error.localizedDescription }
            return false
        }
    }

    func recordSelection(_ option: AccessOption) async {
        let generation = backendGeneration
        let eventID = UUID().uuidString
        do {
            let identity = try await ensureInstallation(generation: generation)
            try requireCurrent(identity, generation: generation)
            try await client.recordSelection(option, eventID: eventID, installation: identity)
            await refreshStatistics()
        } catch {
            // An unavailable statistics endpoint must not block a purchase or
            // turn an unconfirmed tap into fabricated public usage numbers.
        }
    }

    /// Reporting uses the anonymous device identity, independently of a
    /// purchase, a free-access request or an active reading entitlement.
    func submitTextReport(_ report: TextReportRequest) async throws {
        try report.validate()
        let generation = backendGeneration
        let identity = try await ensureInstallation(generation: generation)
        try requireCurrent(identity, generation: generation)
        try await client.submitTextReport(report, installation: identity)
        try requireCurrent(identity, generation: generation)
    }

    func recoverFreeAccess(_ code: String) async {
        guard !isBusy, !isLoading else { return }
        isBusy = true
        let generation = beginBackendMutation()
        notice = nil
        errorMessage = nil
        defer { isBusy = false }
        do {
            let recovered = try await client.recover(code)
            guard generation == backendGeneration else { throw ObsoleteBackendResult() }
            try AccessKeychain.save(recovered, account: "installation", service: client.keychainService)
            installation = recovered
            recoveryCode = recovered.shareableRecoveryCode
            freeGrant = nil
            verifiedAt = nil
            try AccessKeychain.delete(account: "grant", service: client.keychainService)
            try save(await client.status(for: recovered), for: recovered, generation: generation)
            try AccessKeychain.save(false, account: "retain-revenuecat-user", service: client.keychainService)
            retainPurchasesIdentity = false
            await identifyPurchases(as: recovered.revenuecatAppUserID)
            notice = hasAccess ? "Dein Zugang wurde wiederhergestellt."
                : "Dein Zugangscode wurde wiederhergestellt. Es besteht derzeit kein aktiver Gratiszugang; du kannst jederzeit anfragen."
        } catch { errorMessage = error.localizedDescription }
    }

    func deleteFreeAccessData() async {
        guard !isBusy, !isLoading else { return }
        isBusy = true
        _ = beginBackendMutation()
        notice = nil
        errorMessage = nil
        defer { isBusy = false }
        do {
            if let installation { try await client.deleteInstallation(installation) }
            try AccessKeychain.save(true, account: "retain-revenuecat-user", service: client.keychainService)
            retainPurchasesIdentity = true
            self.installation = nil
            freeGrant = nil
            verifiedAt = nil
            recoveryCode = nil
            pendingRequest = nil
            try AccessKeychain.delete(account: "installation", service: client.keychainService)
            try AccessKeychain.delete(account: "grant", service: client.keychainService)
            // Keep Apple purchases under their existing RevenueCat identity.
            // Deleting private free-access data does not cancel an Apple abo.
            notice = "Deine kostenlosen Zugangsdaten und Bitten wurden gelöscht. Ein Apple-Abo kannst du unter „Abo verwalten“ kündigen."
        } catch { errorMessage = error.localizedDescription }
    }

    private func loadSavedAccess() throws {
        retainPurchasesIdentity = try AccessKeychain.load(Bool.self, account: "retain-revenuecat-user", service: client.keychainService) ?? false
        installation = try AccessKeychain.load(AccessInstallation.self, account: "installation", service: client.keychainService)
        recoveryCode = installation?.shareableRecoveryCode
        if let cached = try AccessKeychain.load(CachedGrant.self, account: "grant", service: client.keychainService),
           cached.grant.revenuecatAppUserID == installation?.revenuecatAppUserID {
            freeGrant = cached.grant
            verifiedAt = cached.verifiedAt
        }
    }

    private struct ObsoleteBackendResult: Error {}
    private struct PendingInstallation {
        let id: UUID
        let generation: UInt64
        let task: Task<AccessInstallation, Error>
    }
    @ObservationIgnored private var installationTask: PendingInstallation?

    private func beginBackendMutation() -> UInt64 {
        backendGeneration &+= 1
        // Do not cancel a sent creation request: its eventual response lets us
        // delete the obsolete server identity without retaining its credential.
        installationTask = nil
        return backendGeneration
    }

    private func requireCurrent(_ identity: AccessInstallation, generation: UInt64) throws {
        guard generation == backendGeneration,
              installation?.installationID == identity.installationID,
              installation?.accessToken == identity.accessToken else { throw ObsoleteBackendResult() }
    }

    private func ensureInstallation(generation: UInt64) async throws -> AccessInstallation {
        guard generation == backendGeneration else { throw ObsoleteBackendResult() }
        if let installation { return installation }
        if let pending = installationTask, pending.generation == generation {
            let identity = try await pending.task.value
            try requireCurrent(identity, generation: generation)
            return identity
        }
        // Prevent parallel product/status/selection work from creating more
        // than one identity for the same installation.
        let task = Task { @MainActor in
            guard generation == backendGeneration else { throw ObsoleteBackendResult() }
            try loadSavedAccess()
            if let installation { return installation }
            let created = try await client.createInstallation()
            guard generation == backendGeneration else {
                try? await client.deleteInstallation(created)
                throw ObsoleteBackendResult()
            }
            try AccessKeychain.save(created, account: "installation", service: client.keychainService)
            installation = created
            recoveryCode = created.shareableRecoveryCode
            return created
        }
        let taskID = UUID()
        installationTask = PendingInstallation(id: taskID, generation: generation, task: task)
        defer { if installationTask?.id == taskID { installationTask = nil } }
        let identity = try await task.value
        try requireCurrent(identity, generation: generation)
        return identity
    }

    private func refreshBackend() async {
        let generation = backendGeneration
        var requestedIdentity: AccessInstallation?
        do {
            let identity = try await ensureInstallation(generation: generation)
            requestedIdentity = identity
            try save(await client.status(for: identity), for: identity, generation: generation)
            await identifyPurchases(as: identity.revenuecatAppUserID)
        } catch {
            guard generation == backendGeneration, !(error is ObsoleteBackendResult) else { return }
            if let requestedIdentity {
                do { try requireCurrent(requestedIdentity, generation: generation) }
                catch { return }
            }
            if case AccessClientError.httpStatus(401) = error {
                freeGrant = nil
                verifiedAt = nil
                try? AccessKeychain.delete(account: "grant", service: client.keychainService)
            }
            errorMessage = error.localizedDescription
        }
    }

    private func save(_ grant: AccessFreeGrant, for identity: AccessInstallation, generation: UInt64) throws {
        try requireCurrent(identity, generation: generation)
        guard grant.revenuecatAppUserID == identity.revenuecatAppUserID,
              !grant.active || (grant.startsAt != nil && grant.expiresAt != nil && grant.expiresAt! > grant.startsAt!) else {
            throw AccessClientError.invalidResponse
        }
        let now = Date()
        try AccessKeychain.save(CachedGrant(grant: grant, verifiedAt: now), account: "grant", service: client.keychainService)
        freeGrant = grant
        verifiedAt = now
        evaluatedAt = now
    }

    private func refreshStatistics() async { statistics = try? await client.statistics() }

    private static var publicSDKKey: String? {
        let value = (ProcessInfo.processInfo.environment["GA_REVENUECAT_IOS_SDK_KEY"]
                     ?? Bundle.main.object(forInfoDictionaryKey: "GARevenueCatPublicSDKKey") as? String ?? "")
            .trimmingCharacters(in: .whitespacesAndNewlines)
        // Never configure with a RevenueCat secret or Test Store key.
        return value.hasPrefix("appl_") && value.count > 10
            && !value.uppercased().contains("REPLACE") && !value.contains("$(") ? value : nil
    }

    private func configurePurchases() throws {
        if usesLocalStoreKit { return }
        guard let key = Self.publicSDKKey else {
            #if !DEBUG
            throw PurchaseError.notConfigured
            #else
            return
            #endif
        }
        if !Purchases.isConfigured {
            let savedID = try AccessKeychain.load(String.self, account: "revenuecat-user", service: client.keychainService)
            Purchases.logLevel = .warn
            Purchases.configure(with: Configuration.builder(withAPIKey: key)
                .with(appUserID: savedID ?? installation?.revenuecatAppUserID)
                .with(entitlementVerificationMode: .informational)
                .build())
            // RevenueCat's initial anonymous identity can be aliased on login,
            // so a backend outage does not strand an already purchased abo.
            try AccessKeychain.save(Purchases.shared.appUserID, account: "revenuecat-user", service: client.keychainService)
        }
    }

    private func identifyPurchases(as id: String) async {
        guard !retainPurchasesIdentity, !usesLocalStoreKit, Purchases.isConfigured, Purchases.shared.appUserID != id else { return }
        do {
            let result = try await Purchases.shared.logIn(id)
            try AccessKeychain.save(id, account: "revenuecat-user", service: client.keychainService)
            apply(result.customerInfo)
            await loadProducts()
        } catch { errorMessage = purchaseErrorMessage(error) }
    }

    private func refreshPaidAccess() async {
        do {
            if usesLocalStoreKit { await updateStoreKitAccess() }
            else if Purchases.isConfigured { apply(try await Purchases.shared.customerInfo()) }
            await loadProducts()
        } catch { errorMessage = purchaseErrorMessage(error) }
    }

    private func apply(_ info: CustomerInfo) {
        if let entitlement = info.entitlements["ga_access"], entitlement.isActive,
           entitlement.verification.isVerified,
           let expiry = [entitlement.expirationDate,
                         info.subscriptionsByProductIdentifier[entitlement.productIdentifier]?.gracePeriodExpiresDate]
            .compactMap({ $0 }).filter({ $0.timeIntervalSinceReferenceDate.isFinite }).max() {
            paidExpiration = expiry
        } else { paidExpiration = nil }
        if let url = info.managementURL { manageSubscriptionsURL = url }
        evaluatedAt = Date()
    }

    private func loadProducts() async {
        let paidOptions: [AccessOption] = [.annual, .supporter]
        let identifiers = paidOptions.compactMap(\.productID)
        if usesLocalStoreKit {
            do {
                let available = try await Product.products(for: identifiers)
                var mapped: [AccessOption: AccessProduct] = [:]
                storekitProducts = [:]
                for option in paidOptions {
                    guard let product = available.first(where: { $0.id == option.productID }),
                          product.type == .autoRenewable, let subscription = product.subscription,
                          subscription.subscriptionPeriod.unit == .year, subscription.subscriptionPeriod.value == 1 else { continue }
                    let offer = subscription.introductoryOffer
                    let trial = offer?.paymentMode == .freeTrial && offer?.period.unit == .month
                        && (offer?.period.value ?? 0) * (offer?.periodCount ?? 0) == 3
                    let eligible = trial ? await subscription.isEligibleForIntroOffer : false
                    storekitProducts[option] = product
                    mapped[option] = AccessProduct(id: product.id, localizedPrice: product.displayPrice,
                        subscriptionPeriod: "Jahr", eligibleForTrial: eligible, trialDescription: trial ? "3 Monate" : nil)
                }
                products = mapped
            } catch { errorMessage = purchaseErrorMessage(error) }
        } else if Purchases.isConfigured {
            let available = await Purchases.shared.products(identifiers)
            let eligibility = await Purchases.shared.checkTrialOrIntroDiscountEligibility(productIdentifiers: identifiers)
            var mapped: [AccessOption: AccessProduct] = [:]
            revenuecatProducts = [:]
            for option in paidOptions {
                guard let product = available.first(where: { $0.productIdentifier == option.productID }),
                      product.productType == .autoRenewableSubscription,
                      let period = product.subscriptionPeriod, period.unit == .year, period.value == 1 else { continue }
                let offer = product.introductoryDiscount
                let trial = offer?.paymentMode == .freeTrial && offer?.subscriptionPeriod.unit == .month
                    && (offer?.subscriptionPeriod.value ?? 0) * (offer?.numberOfPeriods ?? 0) == 3
                let eligible = trial && eligibility[product.productIdentifier]?.status == .eligible
                revenuecatProducts[option] = product
                mapped[option] = AccessProduct(id: product.productIdentifier, localizedPrice: product.localizedPriceString,
                    subscriptionPeriod: "Jahr", eligibleForTrial: eligible, trialDescription: trial ? "3 Monate" : nil)
            }
            products = mapped
        }
    }

    private func updateStoreKitAccess() async {
        let ids = Set([AccessOption.annual.productID!, AccessOption.supporter.productID!])
        var expiry: Date?
        for await result in StoreKit.Transaction.currentEntitlements {
            guard case .verified(let transaction) = result,
                  ids.contains(transaction.productID), transaction.revocationDate == nil,
                  !transaction.isUpgraded, let expiration = transaction.expirationDate,
                  expiration > Date() else { continue }
            expiry = max(expiry ?? .distantPast, expiration)
        }
        paidExpiration = expiry
        evaluatedAt = Date()
    }

    private func startUpdates() {
        if usesLocalStoreKit {
            updatesTask = Task { [weak self] in
                for await result in StoreKit.Transaction.updates {
                    guard !Task.isCancelled else { return }
                    await self?.updateStoreKitAccess()
                    if case .verified(let transaction) = result { await transaction.finish() }
                    await self?.loadProducts()
                }
            }
        } else if Purchases.isConfigured {
            updatesTask = Task { [weak self] in
                for await info in Purchases.shared.customerInfoStream {
                    guard !Task.isCancelled else { return }
                    self?.apply(info)
                }
            }
        }
        expiryTask = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(30))
                guard !Task.isCancelled else { return }
                self?.evaluatedAt = Date()
            }
        }
    }

    private func purchaseErrorMessage(_ error: any Error) -> String {
        if let error = error as? PurchaseError { return error.localizedDescription }
        return "Der Kauf oder die Wiederherstellung konnte nicht abgeschlossen werden. Bitte prüfe deine Verbindung und versuche es erneut."
    }

    private enum PurchaseError: LocalizedError {
        case notConfigured, productUnavailable, unverified
        var errorDescription: String? {
            switch self {
            case .notConfigured: "Abos sind derzeit nicht verfügbar. Bitte versuche es später erneut."
            case .productUnavailable: "Dieses Abo ist im App Store derzeit nicht verfügbar. Bitte versuche es später erneut."
            case .unverified: "Der Kauf konnte noch nicht bestätigt werden. Es wurde kein Zugang aktiviert."
            }
        }
    }

    deinit { updatesTask?.cancel(); expiryTask?.cancel() }
}
