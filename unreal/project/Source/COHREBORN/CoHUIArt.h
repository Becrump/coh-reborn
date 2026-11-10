// The original City of Heroes UI art and fonts, read at runtime from
// Content/UI (made by tools/ui/export_gui.py; game data, not in git).
//
// FCoHPainter mirrors the original immediate-mode sprite calls
// (display_sprite, display_rotated_sprite, prnt/cprnt, drawFrame...) so the
// original window code in Game/src/UI can be ported nearly line by line:
// positions and scales are in the original's pixel units, colours are the
// original 0xRRGGBBAA ints and the z value orders the sprites.
#pragma once

#include "CoreMinimal.h"
#include "Fonts/SlateFontInfo.h"

struct FSlateBrush;
class FSlateWindowElementList;
struct FGeometry;

/** One original texture: the brush plus its ORIGINAL size (the archive stored
*  most GUI art padded out to a power of two; the PNGs are cropped back and the UI code places by this size). */
struct FCoHTex
{
	TSharedPtr<FSlateBrush> Brush;
	/** A brush owned elsewhere (power icons from the power database). */
	const FSlateBrush* External = nullptr;
	float W = 1.f, H = 1.f;
	const FSlateBrush* Get() const { return Brush.IsValid() ? Brush.Get() : External; }
};

/** The original font contexts (sprite_font.c): game_* is Mont DemiBold,
 *  title_* is Red Circle, both with a 1 px black outline. */
enum class ECoHFont : uint8 { Game, GameBold, Title, Digital, Tiny, Tahoma };

class COHREBORN_API FCoHUIArt
{
public:
	static FCoHUIArt& Get();
	/** Content/UI/ui_art.json exists (the art has been copied in). */
	bool IsAvailable();
	/** By original name, any case, with or without .tga/.texture. Never null:
	 *  a missing name gives the 1x1 white texture (and is logged once). */
	const FCoHTex* Tex(const FString& Name);
	/** The plain white texture the original stretches for boxes and backs. */
	const FCoHTex* White();
	/** PixelSize as in the original (game_12 = 12 px). */
	FSlateFontInfo Font(ECoHFont Kind, float PixelSize, bool bOutline = true);
	static FString Dir();

private:
	void Load();
	bool bLoaded = false;
	struct FEntry { float W = 1.f, H = 1.f; FString Path; };
	TMap<FString, FEntry> Entries;
	TMap<FString, TUniquePtr<FCoHTex>> Cache;   // stable addresses
	TSet<FString> Missing;
	TMap<uint32, FSlateFontInfo> Fonts;
	FCoHTex WhiteTex;
};

/** RGBA int as in the original (0x3399ffff) to a Slate colour. */
COHREBORN_API FLinearColor CoHColor(uint32 Rgba);
/** interp_rgba: Alpha 0 gives A, 1 gives B. */
COHREBORN_API uint32 CoHLerpColor(float Alpha, uint32 A, uint32 B);

namespace CoHText
{
	enum EFlags : uint8 { None = 0, CenterX = 1, CenterY = 2, Right = 4 };
}

class COHREBORN_API FCoHPainter
{
public:
	FCoHPainter();

	// --- the original sprite calls -------------------------------------
	void Sprite(const FCoHTex* T, float X, float Y, float Z, float XSc, float YSc, uint32 Rgba);
	/** Rotated about its centre, angle in radians as in display_rotated_sprite. */
	void Rotated(const FCoHTex* T, float X, float Y, float Z, float XSc, float YSc, uint32 Rgba, float Angle);
	void Box(float X, float Y, float Z, float W, float H, uint32 Rgba);
	/** prnt / cprnt: Y is the text baseline unless CenterY is set. */
	void Text(ECoHFont Font, float Px, float X, float Y, float Z, float Sc, uint32 Rgba, const FString& S, uint8 Flags = CoHText::None);
	static float TextWidth(ECoHFont Font, float Px, float Sc, const FString& S);
	/** set_scissor / scissor_dims: clips everything added until NoClip. */
	void Clip(float X, float Y, float W, float H);
	void NoClip();

	// --- ported helpers (uiUtilGame.c) -----------------------------------
	/** drawFrame: the window frame of Size px border (2 or 3) and Radius (4, 6, 10, 16, 22, 27). */
	void Frame(int32 Size, int32 Radius, float X, float Y, float Z, float Wd, float Ht, float Sc, uint32 Color, uint32 BackColor);
	/** drawBar: the glossy slider used by every meter. */
	void Bar(float X, float Y, float Z, float Width, float Sc, float Percentage, float GlowScale, uint32 Color);
	/** drawCapsule (target window bars), without the number text. */
	void Capsule(float X, float Y, float Z, float Wd, float Sc, uint32 Color, uint32 BackColor, uint32 BarColor, float Fraction);

	/** Draws everything, lowest z first (insertion order inside one z). */
	int32 Flush(const FGeometry& Geometry, FSlateWindowElementList& Out, int32 Layer) const;

private:
	enum class EKind : uint8 { Sprite, Rotated, Text };
	struct FItem
	{
		EKind Kind = EKind::Sprite;
		float Z = 0;
		int32 Order = 0;
		const FSlateBrush* Brush = nullptr;
		FVector2f Pos, Size;
		FLinearColor Colour;
		float Angle = 0;
		FString Text;
		FSlateFontInfo Font;
		int32 ClipIndex = INDEX_NONE;
	};
	TArray<FItem> Items;
	TArray<FBox2f> Clips;
	int32 CurrentClip = INDEX_NONE;
};
