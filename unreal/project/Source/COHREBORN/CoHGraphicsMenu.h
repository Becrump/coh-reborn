#pragma once
#include "CoreMinimal.h"
#include "UObject/Object.h"
#include "CoHGraphicsMenu.generated.h"

/** Small native settings panel; settings persist through GameUserSettings. */
UCLASS()
class COHREBORN_API UCoHGraphicsMenu : public UObject
{
    GENERATED_BODY()
public:
    void Toggle(class APlayerController* Controller);
    void Close();
    UFUNCTION(BlueprintCallable, Category="CoH|Settings")
    void ApplyQuality(int32 Quality);
    UFUNCTION(BlueprintCallable, Category="CoH|Settings")
    void ApplyDensity(float Crowd, float Traffic);
    /** Comic look on every post-process volume that carries the comic
     *  material: 0 off, 1 light (the old Atlas Park look), 2 strong
     *  (paint smoothing flattens texture noise, firmer ink), 3 vibrant
     *  (more saturation and contrast, warm lights, cool shadows). Saved. */
    UFUNCTION(BlueprintCallable, Category="CoH|Settings")
    static void ApplyComic(UObject* WorldContext, int32 Mode);
    static int32 SavedComic();
private:
    TSharedPtr<class SWidget> Panel;
    TWeakObjectPtr<class APlayerController> Player;
};
