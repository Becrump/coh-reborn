#include "CoHUIArt.h"

#include "Brushes/SlateDynamicImageBrush.h"
#include "Dom/JsonObject.h"
#include "Fonts/FontMeasure.h"
#include "Framework/Application/SlateApplication.h"
#include "HAL/FileManager.h"
#include "Layout/Geometry.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Rendering/DrawElements.h"
#include "Rendering/SlateRenderer.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Styling/CoreStyle.h"

DEFINE_LOG_CATEGORY_STATIC(LogCoHUI, Log, All);

// ---------------------------------------------------------------------------
// colours

FLinearColor CoHColor(uint32 Rgba)
{
	// the original colours are sRGB bytes; Slate tints are linear
	return FLinearColor(FColor((Rgba >> 24) & 0xff, (Rgba >> 16) & 0xff, (Rgba >> 8) & 0xff, Rgba & 0xff));
}

uint32 CoHLerpColor(float Alpha, uint32 A, uint32 B)
{
	Alpha = FMath::Clamp(Alpha, 0.f, 1.f);
	uint32 Out = 0;
	for (int32 Shift = 0; Shift < 32; Shift += 8)
	{
		const float Ca = (A >> Shift) & 0xff, Cb = (B >> Shift) & 0xff;
		Out |= (uint32(FMath::RoundToInt(Ca + (Cb - Ca) * Alpha)) & 0xff) << Shift;
	}
	return Out;
}

// ---------------------------------------------------------------------------
// art

FCoHUIArt& FCoHUIArt::Get()
{
	static FCoHUIArt Art;
	return Art;
}

FString FCoHUIArt::Dir()
{
	return FPaths::ConvertRelativePathToFull(FPaths::ProjectContentDir() / TEXT("UI"));
}

void FCoHUIArt::Load()
{
	if (bLoaded) return;
	bLoaded = true;

	WhiteTex.Brush = MakeShared<FSlateBrush>(*FCoreStyle::Get().GetBrush("WhiteBrush"));
	WhiteTex.W = WhiteTex.H = 1.f;

	FString Json;
	const FString Manifest = Dir() / TEXT("ui_art.json");
	if (!FFileHelper::LoadFileToString(Json, *Manifest))
	{
		UE_LOG(LogCoHUI, Warning, TEXT("Original UI art not found (%s): run tools/ui/export_gui.py and copy its output to Content/UI. Using the plain HUD."), *Manifest);
		return;
	}
	TSharedPtr<FJsonObject> Root;
	if (!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Json), Root) || !Root.IsValid())
	{
		UE_LOG(LogCoHUI, Error, TEXT("Could not read %s"), *Manifest);
		return;
	}
	for (const auto& Pair : Root->Values)
	{
		const TArray<TSharedPtr<FJsonValue>>* A = nullptr;
		if (!Pair.Value->TryGetArray(A) || A->Num() < 3) continue;
		FEntry E;
		E.W = (float)(*A)[0]->AsNumber();
		E.H = (float)(*A)[1]->AsNumber();
		E.Path = Dir() / (*A)[2]->AsString();
		Entries.Add(FString(Pair.Key).ToLower(), E);
	}
	UE_LOG(LogCoHUI, Log, TEXT("Original UI art: %d textures"), Entries.Num());
}

bool FCoHUIArt::IsAvailable()
{
	Load();
	return Entries.Num() > 0;
}

const FCoHTex* FCoHUIArt::White()
{
	Load();
	return &WhiteTex;
}

const FCoHTex* FCoHUIArt::Tex(const FString& InName)
{
	Load();
	FString Key = FPaths::GetBaseFilename(InName).ToLower();
	if (Key == TEXT("white")) return &WhiteTex;
	if (const TUniquePtr<FCoHTex>* Hit = Cache.Find(Key)) return Hit->Get();
	const FEntry* E = Entries.Find(Key);
	if (!E)
	{
		if (!Missing.Contains(Key))
		{
			Missing.Add(Key);
			UE_LOG(LogCoHUI, Warning, TEXT("UI texture missing: %s"), *InName);
		}
		return &WhiteTex;
	}
	TUniquePtr<FCoHTex> T = MakeUnique<FCoHTex>();
	// Slate reads the PNG itself on first draw (as the loading screen does)
	T->Brush = MakeShared<FSlateDynamicImageBrush>(FName(*E->Path), FVector2D(E->W, E->H));
	T->W = E->W;
	T->H = E->H;
	return Cache.Add(Key, MoveTemp(T)).Get();
}

FSlateFontInfo FCoHUIArt::Font(ECoHFont Kind, float PixelSize, bool bOutline)
{
	const uint32 Key = (uint32(Kind) << 24) | (uint32(bOutline) << 23) | (uint32(FMath::RoundToInt(PixelSize * 10.f)) & 0x7fffff);
	if (const FSlateFontInfo* Hit = Fonts.Find(Key)) return *Hit;
	const TCHAR* File = TEXT("mont_demibold.ttf");
	switch (Kind)
	{
	case ECoHFont::GameBold: File = TEXT("mont_hvbold.ttf"); break;
	case ECoHFont::Title:    File = TEXT("redcircl.ttf"); break;
	case ECoHFont::Digital:  File = TEXT("digitalb.ttf"); break;
	case ECoHFont::Tiny:     File = TEXT("slkscr.ttf"); break;
	case ECoHFont::Tahoma:   File = TEXT("tahoma.ttf"); break;
	default: break;
	}
	const FString Path = Dir() / TEXT("fonts") / File;
	// the original sizes are pixels; Slate sizes are points at 96 dpi
	const float Points = FMath::Max(1.f, PixelSize * 0.75f);
	FSlateFontInfo F = FPaths::FileExists(Path)
		? FSlateFontInfo(Path, Points)
		: FCoreStyle::GetDefaultFontStyle(Kind == ECoHFont::Game ? "Regular" : "Bold", FMath::RoundToInt(Points));
	if (bOutline)
	{
		F.OutlineSettings.OutlineSize = 1;
		F.OutlineSettings.OutlineColor = FLinearColor::Black;
	}
	Fonts.Add(Key, F);
	return F;
}

// ---------------------------------------------------------------------------
// painter

FCoHPainter::FCoHPainter() { Items.Reserve(512); }

void FCoHPainter::Sprite(const FCoHTex* T, float X, float Y, float Z, float XSc, float YSc, uint32 Rgba)
{
	if (!T || !T->Get() || (Rgba & 0xff) == 0) return;
	const float W = T->W * XSc, H = T->H * YSc;
	if (W <= 0.f || H <= 0.f) return;
	FItem& I = Items.AddDefaulted_GetRef();
	I.Kind = EKind::Sprite;
	I.Z = Z;
	I.Order = Items.Num();
	I.Brush = T->Get();
	I.Pos = FVector2f(X, Y);
	I.Size = FVector2f(W, H);
	I.Colour = CoHColor(Rgba);
	I.ClipIndex = CurrentClip;
}

void FCoHPainter::Rotated(const FCoHTex* T, float X, float Y, float Z, float XSc, float YSc, uint32 Rgba, float Angle)
{
	Sprite(T, X, Y, Z, XSc, YSc, Rgba);
	if (Items.Num() && Items.Last().Order == Items.Num())
	{
		Items.Last().Kind = EKind::Rotated;
		Items.Last().Angle = Angle;
	}
}

void FCoHPainter::Box(float X, float Y, float Z, float W, float H, uint32 Rgba)
{
	Sprite(FCoHUIArt::Get().White(), X, Y, Z, W, H, Rgba);
}

static FVector2f MeasureText(const FSlateFontInfo& Font, const FString& S, float& OutAscent)
{
	OutAscent = 0.f;
	if (!FSlateApplication::IsInitialized()) return FVector2f::ZeroVector;
	const TSharedRef<FSlateFontMeasure> M = FSlateApplication::Get().GetRenderer()->GetFontMeasureService();
	const float MaxH = (float)M->GetMaxCharacterHeight(Font);
	OutAscent = MaxH + (float)M->GetBaseline(Font);   // baseline is negative, from the bottom
	return FVector2f(M->Measure(S, Font));
}

float FCoHPainter::TextWidth(ECoHFont Font, float Px, float Sc, const FString& S)
{
	float Ascent;
	return MeasureText(FCoHUIArt::Get().Font(Font, Px * Sc), S, Ascent).X;
}

void FCoHPainter::Text(ECoHFont Font, float Px, float X, float Y, float Z, float Sc, uint32 Rgba, const FString& S, uint8 Flags)
{
	if (S.IsEmpty() || (Rgba & 0xff) == 0) return;
	FItem& I = Items.AddDefaulted_GetRef();
	I.Kind = EKind::Text;
	I.Z = Z;
	I.Order = Items.Num();
	I.Font = FCoHUIArt::Get().Font(Font, Px * Sc);
	float Ascent;
	const FVector2f Size = MeasureText(I.Font, S, Ascent);
	float Left = X, Top = Y - Ascent;
	if (Flags & CoHText::CenterX) Left = X - Size.X * 0.5f;
	else if (Flags & CoHText::Right) Left = X - Size.X;
	if (Flags & CoHText::CenterY) Top = Y - Size.Y * 0.5f;
	I.Pos = FVector2f(Left, Top);
	I.Size = FVector2f(Size.X + 4.f, Size.Y + 4.f);
	I.Colour = CoHColor(Rgba);
	I.Text = S;
	I.ClipIndex = CurrentClip;
}

void FCoHPainter::Clip(float X, float Y, float W, float H)
{
	CurrentClip = Clips.Add(FBox2f(FVector2f(X, Y), FVector2f(X + W, Y + H)));
}

void FCoHPainter::NoClip() { CurrentClip = INDEX_NONE; }

void FCoHPainter::Frame(int32 Size, int32 Radius, float X, float Y, float Z, float Wd, float Ht, float Sc, uint32 Color, uint32 BackColor)
{
	// drawFrameStyle (kFrameStyle_3D), uiUtilGame.c
	FCoHUIArt& A = FCoHUIArt::Get();
	const FString Base = FString::Printf(TEXT("Frame_%dpx_%dr_"), Size, Radius);
	const FCoHTex* UL = A.Tex(Base + TEXT("UL"));
	const FCoHTex* UR = A.Tex(Base + TEXT("UR"));
	const FCoHTex* LL = A.Tex(Base + TEXT("LL"));
	const FCoHTex* LR = A.Tex(Base + TEXT("LR"));
	const FCoHTex* BUL = A.Tex(Base + TEXT("Background_UL"));
	const FCoHTex* BUR = A.Tex(Base + TEXT("Background_UR"));
	const FCoHTex* BLL = A.Tex(Base + TEXT("Background_LL"));
	const FCoHTex* BLR = A.Tex(Base + TEXT("Background_LR"));
	const FCoHTex* YPipe = A.Tex(FString::Printf(TEXT("Frame_%dpx_vert"), Size));
	const FCoHTex* XPipe = A.Tex(FString::Printf(TEXT("Frame_%dpx_horiz"), Size));
	const FCoHTex* Back = A.White();

	const float W = UL->W;
	float XSc = Sc, YSc = Sc;
	if (Wd < W * 2 * Sc) XSc = Wd / (W * 2);
	if (Ht < W * 2 * Sc) YSc = Ht / (W * 2);

	// middle
	Sprite(Back, X + W * XSc, Y + W * YSc, Z, (Wd - 2 * W * XSc) / Back->W, (Ht - 2 * W * YSc) / Back->H, BackColor);
	// top left
	Sprite(BUL, X, Y, Z, XSc, YSc, BackColor);
	Sprite(UL, X, Y, Z, XSc, YSc, Color);
	// top
	Sprite(Back, X + W * XSc, Y + Size * YSc, Z, (Wd - 2 * W * XSc) / Back->W, (W - Size) * YSc / Back->H, BackColor);
	Sprite(XPipe, X + W * XSc, Y, Z, (Wd - 2 * W * XSc) / XPipe->W, YSc, Color);
	// top right
	Sprite(BUR, X + Wd - W * XSc, Y, Z, XSc, YSc, BackColor);
	Sprite(UR, X + Wd - W * XSc, Y, Z, XSc, YSc, Color);
	// right
	Sprite(Back, X + Wd - W * XSc, Y + W * YSc, Z, (W - Size) * XSc / Back->W, (Ht - 2 * W * YSc) / Back->H, BackColor);
	Sprite(YPipe, X + Wd - Size * XSc, Y + W * YSc, Z, XSc, (Ht - 2 * W * YSc) / YPipe->H, Color);
	// lower right
	Sprite(BLR, X + Wd - W * XSc, Y + Ht - W * YSc, Z, XSc, YSc, BackColor);
	Sprite(LR, X + Wd - W * XSc, Y + Ht - W * YSc, Z, XSc, YSc, Color);
	// bottom
	Sprite(Back, X + W * XSc, Y + Ht - W * YSc, Z, (Wd - 2 * W * XSc) / Back->W, (W - Size) * YSc / Back->H, BackColor);
	Sprite(XPipe, X + W * XSc, Y + Ht - Size * YSc, Z, (Wd - 2 * W * XSc) / XPipe->W, YSc, Color);
	// lower left
	Sprite(BLL, X, Y + Ht - W * YSc, Z, XSc, YSc, BackColor);
	Sprite(LL, X, Y + Ht - W * YSc, Z, XSc, YSc, Color);
	// left
	Sprite(Back, X + Size * XSc, Y + W * YSc, Z, (W - Size) * XSc / Back->W, (Ht - 2 * W * YSc) / Back->H, BackColor);
	Sprite(YPipe, X, Y + W * YSc, Z, XSc, (Ht - 2 * W * YSc) / YPipe->H, Color);
}

void FCoHPainter::Bar(float X, float Y, float Z, float Width, float Sc, float Percentage, float GlowScale, uint32 Color)
{
	// drawBar, uiUtilGame.c (the positive direction)
	FCoHUIArt& A = FCoHUIArt::Get();
	const FCoHTex* BarT = A.Tex(TEXT("healthbar_slider"));
	const FCoHTex* Shine = A.Tex(TEXT("healthbar_sliderhighlight"));
	const FCoHTex* Glow = A.Tex(TEXT("healthbar_glow"));
	const float Len = Percentage * (Width - 8 * Sc);

	Sprite(BarT, X + 5 * Sc, Y + 4 * Sc, Z - 1, Len / BarT->W, Sc, 0x000000ff);     // drop shadow
	Sprite(BarT, X + 4 * Sc, Y + 4 * Sc, Z, Len / BarT->W, Sc, Color);
	Sprite(Shine, X + 4 * Sc, Y + 4 * Sc, Z + 1, Len / Shine->W, Sc, 0xffffffff);
	if (GlowScale > 0.f)
	{
		Sprite(Glow, X + 4 * Sc + Len - GlowScale * Glow->W * Sc / 2, Y + 6 * Sc + GlowScale * Sc * (BarT->W - Glow->W) / 2, Z, GlowScale * Sc, GlowScale * Sc, Color);
		const float G = GlowScale * 0.8f;
		Sprite(Glow, X + 4 * Sc + Len - G * Glow->W * Sc / 2, Y + 6 * Sc + G * Sc * (BarT->W - Glow->W) / 2, Z, G * Sc, G * Sc, 0xffffffff);
	}
}

void FCoHPainter::Capsule(float X, float Y, float Z, float Wd, float Sc, uint32 Color, uint32 BackColor, uint32 BarColor, float Fraction)
{
	// drawCapsuleFrame + drawCapsuleEx, uiUtilGame.c
	FCoHUIArt& A = FCoHUIArt::Get();
	const FCoHTex* Left = A.Tex(TEXT("healthbar_framemain_L"));
	const FCoHTex* Right = A.Tex(TEXT("healthbar_framemain_R"));
	const FCoHTex* Pipe = A.Tex(TEXT("healthbar_framemain_horiz"));
	const FCoHTex* Back = A.White();
	const FCoHTex* BarT = A.Tex(TEXT("healthbar_slider"));
	const FCoHTex* Shine = A.Tex(TEXT("healthbar_sliderhighlight"));
	const FCoHTex* Cap = A.Tex(TEXT("healthbar_slider_cap"));
	if (Wd <= Cap->W * 2 * Sc) return;

	const float FZ = Z + 2;
	Sprite(Left, X, Y, FZ, Sc, Sc, Color);
	Sprite(Right, X + Wd - Right->W * Sc, Y, FZ, Sc, Sc, Color);
	Sprite(Pipe, X + Left->W * Sc, Y + 2 * Sc, FZ, (Wd - Sc * (Left->W + Right->W)) / Pipe->W, Sc, Color);
	Sprite(Pipe, X + Left->W * Sc, Y - 2 * Sc + (Left->H - Pipe->H) * Sc, FZ, (Wd - Sc * (Left->W + Right->W)) / Pipe->W, Sc, Color);
	Sprite(Back, X + (2 + Pipe->W) * Sc, Y + (Pipe->H + 2) * Sc, FZ - 2, (Wd - Sc * 4 * Pipe->W) / Back->W, Sc * (Left->H - 4 * Pipe->H) / Back->H, BackColor);

	const float Cur = FMath::Clamp(Fraction, 0.f, 1.f);
	const float Len = Cur * (Wd - (8 + Cap->W) * Sc);
	if (Len >= 0.f && Cur > 0.f)
	{
		Sprite(BarT, X + 4 * Sc, Y + 4 * Sc, Z, Len / BarT->W, Sc, BarColor);
		Sprite(Shine, X + 4 * Sc, Y + 4 * Sc, Z + 1, Cur * (Wd - 8 * Sc) / Shine->W, Sc, 0xffffffff);
		Sprite(Cap, X + 4 * Sc + Len, Y + 4 * Sc, Z, Sc, Sc, BarColor);
	}
}

int32 FCoHPainter::Flush(const FGeometry& Geometry, FSlateWindowElementList& Out, int32 Layer) const
{
	TArray<const FItem*> Sorted;
	Sorted.Reserve(Items.Num());
	for (const FItem& I : Items) Sorted.Add(&I);
	Sorted.Sort([](const FItem& A, const FItem& B) { return A.Z != B.Z ? A.Z < B.Z : A.Order < B.Order; });

	int32 L = Layer;
	int32 OpenClip = INDEX_NONE;
	for (const FItem* I : Sorted)
	{
		if (I->ClipIndex != OpenClip)
		{
			if (OpenClip != INDEX_NONE) Out.PopClip();
			OpenClip = I->ClipIndex;
			if (OpenClip != INDEX_NONE)
			{
				const FBox2f& C = Clips[OpenClip];
				const FSlateRect R = FSlateRect(
					FVector2D(Geometry.LocalToAbsolute(FVector2D(C.Min))),
					FVector2D(Geometry.LocalToAbsolute(FVector2D(C.Max))));
				Out.PushClip(FSlateClippingZone(R));
			}
		}
		++L;   // one layer each keeps the original z order exactly
		const FPaintGeometry PG = Geometry.ToPaintGeometry(I->Size, FSlateLayoutTransform(I->Pos));
		switch (I->Kind)
		{
		case EKind::Sprite:
			FSlateDrawElement::MakeBox(Out, L, PG, I->Brush, ESlateDrawEffect::None, I->Colour);
			break;
		case EKind::Rotated:
			FSlateDrawElement::MakeRotatedBox(Out, L, PG, I->Brush, ESlateDrawEffect::None, I->Angle,
				TOptional<FVector2f>(), FSlateDrawElement::RelativeToElement, I->Colour);
			break;
		case EKind::Text:
			FSlateDrawElement::MakeText(Out, L, PG, I->Text, I->Font, ESlateDrawEffect::None, I->Colour);
			break;
		}
	}
	if (OpenClip != INDEX_NONE) Out.PopClip();
	return L;
}
