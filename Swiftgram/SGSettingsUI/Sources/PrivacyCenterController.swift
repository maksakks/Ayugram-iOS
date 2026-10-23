// MARK: Swiftgram
import SGSimpleSettings
import SGStrings

import SGItemListUI
import Foundation
import UIKit
import Display
import SwiftSignalKit
import Postbox
import TelegramCore
import TelegramPresentationData
import TelegramUIPreferences
import ItemListUI
import PresentationDataUtils
import AccountContext
import UndoUI

// Privacy Center groups client-side privacy options by how reliably the client can honour them.
// Only toggles backed by real code paths are shown; everything the server controls is listed as text.

private enum PrivacyCenterSection: Int32, SGItemListSection {
    case intro
    case supported
    case partial
    case unsupported
    case official
}

private enum PrivacyCenterBoolSetting: String {
    case hidePhoneInSettings
    case warnOnStoriesOpen
    case storyStealthMode
}

private enum PrivacyCenterLink: String {
    case telegramPrivacySettings
}

private typealias PrivacyCenterEntry = SGItemListUIEntry<PrivacyCenterSection, PrivacyCenterBoolSetting, AnyHashable, AnyHashable, PrivacyCenterLink, AnyHashable>

private func privacyCenterEntries(presentationData: PresentationData, sgUISettings: SGUISettings) -> [PrivacyCenterEntry] {
    let lang = presentationData.strings.baseLanguageCode
    let strings = presentationData.strings
    var entries: [PrivacyCenterEntry] = []
    let id = SGItemListCounter()

    entries.append(.notice(id: id.count, section: .intro, text: i18n("PrivacyCenter.Intro", lang)))

    entries.append(.header(id: id.count, section: .supported, text: i18n("PrivacyCenter.Supported.Header", lang), badge: nil))
    entries.append(.toggle(id: id.count, section: .supported, settingName: .hidePhoneInSettings, value: SGSimpleSettings.shared.hidePhoneInSettings, text: i18n("Settings.HidePhoneInSettingsUI", lang), enabled: true))
    entries.append(.toggle(id: id.count, section: .supported, settingName: .warnOnStoriesOpen, value: sgUISettings.warnOnStoriesOpen, text: i18n("Settings.Stories.WarnBeforeView", lang), enabled: true))
    entries.append(.notice(id: id.count, section: .supported, text: i18n("PrivacyCenter.Supported.Notice", lang)))

    if SGSimpleSettings.shared.canUseStealthMode {
        entries.append(.header(id: id.count, section: .partial, text: i18n("PrivacyCenter.Partial.Header", lang), badge: nil))
        entries.append(.toggle(id: id.count, section: .partial, settingName: .storyStealthMode, value: SGSimpleSettings.shared.storyStealthMode, text: strings.Story_StealthMode_Title, enabled: true))
        entries.append(.notice(id: id.count, section: .partial, text: i18n("PrivacyCenter.Partial.StealthNotice", lang)))
    } else {
        id.increment(3)
    }

    entries.append(.header(id: id.count, section: .unsupported, text: i18n("PrivacyCenter.Unsupported.Header", lang), badge: nil))
    entries.append(.notice(id: id.count, section: .unsupported, text: i18n("PrivacyCenter.Unsupported.List", lang)))

    entries.append(.header(id: id.count, section: .official, text: i18n("PrivacyCenter.Official.Header", lang), badge: nil))
    entries.append(.disclosure(id: id.count, section: .official, link: .telegramPrivacySettings, text: strings.Settings_PrivacySettings))
    entries.append(.notice(id: id.count, section: .official, text: i18n("PrivacyCenter.Official.Notice", lang)))

    return entries
}

public func privacyCenterController(context: AccountContext) -> ViewController {
    var presentControllerImpl: ((ViewController, ViewControllerPresentationArguments?) -> Void)?
    var pushControllerImpl: ((ViewController) -> Void)?
    var askForRestart: (() -> Void)?

    // SGSimpleSettings is UserDefaults-backed and not observable, so changes re-trigger the list manually.
    let simplePromise = ValuePromise(true, ignoreRepeated: false)

    let arguments = SGItemListArguments<PrivacyCenterBoolSetting, AnyHashable, AnyHashable, PrivacyCenterLink, AnyHashable>(
        context: context,
        setBoolValue: { setting, value in
            switch setting {
            case .hidePhoneInSettings:
                SGSimpleSettings.shared.hidePhoneInSettings = value
                askForRestart?()
            case .warnOnStoriesOpen:
                let _ = (
                    updateSGUISettings(engine: context.engine, { settings in
                        var settings = settings
                        settings.warnOnStoriesOpen = value
                        return settings
                    })
                ).start()
            case .storyStealthMode:
                SGSimpleSettings.shared.storyStealthMode = value
            }
            simplePromise.set(true)
        },
        openDisclosureLink: { link in
            switch link {
            case .telegramPrivacySettings:
                pushControllerImpl?(context.sharedContext.makePrivacyAndSecurityController(context: context))
            }
        }
    )

    let preferences = context.account.postbox.preferencesView(keys: [ApplicationSpecificPreferencesKeys.SGUISettings])

    let signal = combineLatest(simplePromise.get(), context.sharedContext.presentationData, preferences)
    |> map { _, presentationData, view -> (ItemListControllerState, (ItemListNodeState, Any)) in
        let sgUISettings: SGUISettings = view.values[ApplicationSpecificPreferencesKeys.SGUISettings]?.get(SGUISettings.self) ?? SGUISettings.default

        let entries = privacyCenterEntries(presentationData: presentationData, sgUISettings: sgUISettings)

        let controllerState = ItemListControllerState(presentationData: ItemListPresentationData(presentationData), title: .text(i18n("PrivacyCenter.Title", presentationData.strings.baseLanguageCode)), leftNavigationButton: nil, rightNavigationButton: nil, backNavigationButton: ItemListBackButton(title: presentationData.strings.Common_Back))
        let listState = ItemListNodeState(presentationData: ItemListPresentationData(presentationData), entries: entries, style: .blocks, ensureVisibleItemTag: nil, initialScrollToItem: nil)

        return (controllerState, (listState, arguments))
    }

    let controller = ItemListController(context: context, state: signal)
    presentControllerImpl = { [weak controller] c, a in
        controller?.present(c, in: .window(.root), with: a)
    }
    pushControllerImpl = { [weak controller] c in
        (controller?.navigationController as? NavigationController)?.pushViewController(c)
    }
    askForRestart = { [weak context] in
        guard let context = context else {
            return
        }
        let presentationData = context.sharedContext.currentPresentationData.with { $0 }
        presentControllerImpl?(
            UndoOverlayController(
                presentationData: presentationData,
                content: .info(title: nil,
                    text: i18n("Common.RestartRequired", presentationData.strings.baseLanguageCode),
                    timeout: nil,
                    customUndoText: i18n("Common.RestartNow", presentationData.strings.baseLanguageCode)
                ),
                elevatedLayout: false,
                action: { action in if action == .undo { exit(0) }; return true }
            ),
            nil
        )
    }
    return controller
}
